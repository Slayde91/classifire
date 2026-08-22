package au.com.classifire.admissionsigner;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.hardware.biometrics.BiometricManager;
import android.hardware.biometrics.BiometricPrompt;
import android.net.Uri;
import android.os.Bundle;
import android.os.CancellationSignal;
import android.security.keystore.KeyInfo;
import android.view.Gravity;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.security.KeyFactory;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.time.Instant;
import java.util.Base64;
import java.util.Map;

/** Offline-only admission review, biometric signing, local verification, and export UI. */
public final class OfflineSignerActivity extends Activity {
    private static final int OPEN_MANIFEST = 1001;
    private static final int SAVE_MANIFEST = 1002;
    private static final String PRODUCTION_ALIAS_PREFIX = "classifire_admission_p256_production_";

    private TextView status;
    private Button signButton;
    private AdmissionManifest pendingManifest;
    private byte[] pendingSignedJson;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        ScrollView scroll = new ScrollView(this);
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setGravity(Gravity.CENTER);
        layout.setPadding(48, 48, 48, 48);

        TextView title = new TextView(this);
        title.setText(R.string.offline_signer_title);
        title.setTextSize(22);
        layout.addView(title);

        TextView notice = new TextView(this);
        notice.setText(R.string.offline_signer_notice);
        notice.setPadding(0, 16, 0, 16);
        layout.addView(notice);

        status = new TextView(this);
        status.setText(R.string.no_manifest_loaded);
        status.setPadding(0, 16, 0, 24);
        status.setTextIsSelectable(true);
        layout.addView(status);

        Button loadButton = new Button(this);
        loadButton.setText(R.string.import_manifest_button);
        loadButton.setOnClickListener(view -> openManifest());
        layout.addView(loadButton);

        signButton = new Button(this);
        signButton.setText(R.string.review_sign_button);
        signButton.setEnabled(false);
        signButton.setOnClickListener(view -> confirmAdmission());
        layout.addView(signButton);

        TextView boundary = new TextView(this);
        boundary.setText(R.string.offline_boundary);
        boundary.setPadding(0, 32, 0, 12);
        layout.addView(boundary);

        Button keySetup = new Button(this);
        keySetup.setText(R.string.open_key_setup_button);
        keySetup.setOnClickListener(view -> startActivity(new Intent(this, MainActivity.class)));
        layout.addView(keySetup);

        scroll.addView(layout);
        setContentView(scroll);
    }

    private void openManifest() {
        clearPending();
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT)
                .addCategory(Intent.CATEGORY_OPENABLE)
                .setType("application/json")
                .putExtra(Intent.EXTRA_LOCAL_ONLY, true);
        startActivityForResult(intent, OPEN_MANIFEST);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (resultCode != RESULT_OK || data == null || data.getData() == null) {
            if (requestCode == SAVE_MANIFEST) {
                AdmissionManifest manifest = pendingManifest;
                pendingSignedJson = null;
                restoreSignableManifest(manifest);
                status.setText(R.string.signed_export_cancelled);
            }
            return;
        }
        if (requestCode == OPEN_MANIFEST) loadManifest(data.getData());
        if (requestCode == SAVE_MANIFEST) saveSignedManifest(data.getData());
    }

    private void loadManifest(Uri uri) {
        clearPending();
        try (InputStream input = getContentResolver().openInputStream(uri)) {
            if (input == null) throw new IllegalArgumentException("Selected document cannot be opened");
            AdmissionManifest manifest = AdmissionManifest.parse(readBounded(input), Instant.now());
            KeyMaterial key = productionKey(manifest.value("key_id"), manifest.value("issuer"));
            pendingManifest = manifest;
            signButton.setEnabled(true);
            status.setText(reviewText(manifest, key.fingerprint));
        } catch (Exception exception) {
            status.setText(getString(R.string.manifest_rejected, safeFailure(exception)));
        }
    }

    private void confirmAdmission() {
        AdmissionManifest manifest = pendingManifest;
        if (manifest == null) return;
        try {
            AdmissionManifest.parse(manifest.signedJson(manifest.value("signature")), Instant.now());
            productionKey(manifest.value("key_id"), manifest.value("issuer"));
        } catch (Exception exception) {
            clearPending();
            status.setText(getString(R.string.admission_no_longer_eligible, safeFailure(exception)));
            return;
        }
        new AlertDialog.Builder(this)
                .setTitle(R.string.confirm_admission_title)
                .setMessage(getString(R.string.confirm_admission_message,
                        reviewText(manifest, storedFingerprint(manifest.value("key_id")))))
                .setNegativeButton(R.string.cancel, null)
                .setPositiveButton(R.string.continue_biometric, (dialog, which) -> beginSignature())
                .show();
    }

    private void beginSignature() {
        AdmissionManifest manifest = pendingManifest;
        if (manifest == null) return;
        pendingSignedJson = null;
        signButton.setEnabled(false);
        try {
            KeyMaterial key = productionKey(manifest.value("key_id"), manifest.value("issuer"));
            Signature signature = Signature.getInstance("SHA256withECDSA");
            signature.initSign(key.privateKey);
            BiometricPrompt prompt = new BiometricPrompt.Builder(this)
                    .setTitle(getString(R.string.admission_biometric_title))
                    .setSubtitle(getString(R.string.admission_biometric_subtitle,
                            manifest.value("admission_id"), manifest.expiresAt()))
                    .setAllowedAuthenticators(BiometricManager.Authenticators.BIOMETRIC_STRONG)
                    .build();
            prompt.authenticate(new BiometricPrompt.CryptoObject(signature), new CancellationSignal(),
                    getMainExecutor(), callbackFor(signature, key.publicKey, manifest));
        } catch (Exception exception) {
            clearPending();
            status.setText(getString(R.string.admission_signing_setup_failed, safeFailure(exception)));
        }
    }

    private BiometricPrompt.AuthenticationCallback callbackFor(
            Signature signature, PublicKey publicKey, AdmissionManifest manifest) {
        return new BiometricPrompt.AuthenticationCallback() {
            @Override public void onAuthenticationError(int code, CharSequence error) {
                if (pendingManifest != manifest) return;
                restoreSignableManifest(manifest);
                status.setText(R.string.admission_signing_cancelled);
            }

            @Override public void onAuthenticationSucceeded(BiometricPrompt.AuthenticationResult result) {
                try {
                    if (pendingManifest != manifest || !Instant.now().isBefore(manifest.expiresAt())) {
                        throw new SecurityException("Admission changed or expired during approval");
                    }
                    byte[] bytes = manifest.signingBytes();
                    Signature approved = result.getCryptoObject().getSignature();
                    if (approved != signature) throw new SecurityException("Biometric signature context changed");
                    approved.update(bytes);
                    byte[] canonical = P256Signatures.canonicalLowS(approved.sign());
                    if (!P256Signatures.verifies(bytes, canonical, publicKey)) {
                        throw new SecurityException("Local signature verification failed");
                    }
                    String encoded = Base64.getUrlEncoder().withoutPadding().encodeToString(canonical);
                    pendingSignedJson = manifest.signedJson(encoded);
                    Intent save = new Intent(Intent.ACTION_CREATE_DOCUMENT)
                            .addCategory(Intent.CATEGORY_OPENABLE)
                            .setType("application/json")
                            .putExtra(Intent.EXTRA_LOCAL_ONLY, true)
                            .putExtra(Intent.EXTRA_TITLE,
                                    "admission-" + manifest.value("admission_id") + "-signed.json");
                    startActivityForResult(save, SAVE_MANIFEST);
                } catch (Exception exception) {
                    if (pendingManifest != manifest) return;
                    pendingSignedJson = null;
                    restoreSignableManifest(manifest);
                    status.setText(getString(R.string.admission_signing_failed, safeFailure(exception)));
                }
            }
        };
    }

    private void saveSignedManifest(Uri uri) {
        byte[] signed = pendingSignedJson;
        pendingSignedJson = null;
        if (signed == null) {
            status.setText(R.string.no_verified_signature);
            return;
        }
        try (OutputStream output = getContentResolver().openOutputStream(uri, "wt")) {
            if (output == null) throw new IllegalArgumentException("Selected document cannot be written");
            output.write(signed);
            output.flush();
            status.setText(getString(R.string.signed_manifest_exported, sha256Hex(signed)));
            pendingManifest = null;
            signButton.setEnabled(false);
        } catch (Exception exception) {
            restoreSignableManifest(pendingManifest);
            status.setText(getString(R.string.signed_manifest_export_failed, safeFailure(exception)));
        }
    }

    private KeyMaterial productionKey(String keyId, String issuer) throws Exception {
        if (!issuer.equals(getSharedPreferences("classifire_admission_signer", MODE_PRIVATE)
                .getString("production_issuer_" + keyId, null))) {
            throw new SecurityException("Manifest issuer is not bound to this device key");
        }
        String alias = PRODUCTION_ALIAS_PREFIX + keyId;
        KeyStore store = keyStore();
        if (!store.containsAlias(alias)) throw new SecurityException("Matching device key does not exist");
        PrivateKey privateKey = (PrivateKey) store.getKey(alias, null);
        KeyInfo info = KeyFactory.getInstance(privateKey.getAlgorithm(), "AndroidKeyStore")
                .getKeySpec(privateKey, KeyInfo.class);
        if (!KeystoreSecurity.isHardwareBacked(info)) throw new SecurityException("Key is not secure-hardware backed");
        PublicKey publicKey = store.getCertificate(alias).getPublicKey();
        String fingerprint = sha256Base64url(publicKey.getEncoded());
        if (!fingerprint.equals(storedFingerprint(keyId))) {
            throw new SecurityException("Stored public-key fingerprint does not match Android Keystore");
        }
        return new KeyMaterial(privateKey, publicKey, fingerprint);
    }

    private String storedFingerprint(String keyId) {
        return getSharedPreferences("classifire_admission_signer", MODE_PRIVATE)
                .getString("production_fingerprint_" + keyId, "missing");
    }

    private static byte[] readBounded(InputStream input) throws Exception {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        int count;
        while ((count = input.read(buffer)) != -1) {
            if (output.size() + count > AdmissionManifest.MAX_BYTES) {
                throw new IllegalArgumentException("Manifest exceeds 128 KiB");
            }
            output.write(buffer, 0, count);
        }
        return output.toByteArray();
    }

    private String reviewText(AdmissionManifest manifest, String fingerprint) {
        return getString(
                R.string.validated_admission_review,
                manifest.value("admission_id"),
                manifest.value("project_id"),
                manifest.value("estimate_id"),
                manifest.value("source_run_id"),
                manifest.value("adjudicated_run_id"),
                manifest.value("preflight_receipt_sha256"),
                manifest.value("normalised_submission_payload_sha256"),
                manifest.value("protected_state_fingerprint"),
                manifest.value("protected_state_fingerprint_version"),
                mapText(manifest.stringMap("artifact_digests")),
                mapText(manifest.stringMap("policy_versions")),
                manifest.value("issuer"),
                manifest.value("key_id"),
                fingerprint,
                manifest.issuedAt(),
                manifest.expiresAt()
        );
    }

    private static String mapText(Map<String, String> values) {
        StringBuilder result = new StringBuilder();
        for (Map.Entry<String, String> entry : values.entrySet()) {
            if (result.length() > 0) result.append(", ");
            result.append(entry.getKey()).append('=').append(entry.getValue());
        }
        return result.toString();
    }

    private void restoreSignableManifest(AdmissionManifest manifest) {
        if (manifest == null || pendingManifest != manifest) return;
        pendingSignedJson = null;
        if (!Instant.now().isBefore(manifest.expiresAt())) {
            clearPending();
            return;
        }
        signButton.setEnabled(true);
    }

    private void clearPending() {
        pendingManifest = null;
        pendingSignedJson = null;
        if (signButton != null) signButton.setEnabled(false);
        if (status != null) status.setText(R.string.no_manifest_loaded);
    }

    private static KeyStore keyStore() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        return store;
    }

    private static String sha256Base64url(byte[] value) throws Exception {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(
                MessageDigest.getInstance("SHA-256").digest(value));
    }

    private static String sha256Hex(byte[] value) throws Exception {
        StringBuilder result = new StringBuilder();
        for (byte item : MessageDigest.getInstance("SHA-256").digest(value)) {
            result.append(String.format("%02X", item));
        }
        return result.toString();
    }

    private static String safeFailure(Exception exception) {
        String detail = exception.getMessage();
        if (detail == null || detail.isBlank()) return exception.getClass().getSimpleName();
        return exception.getClass().getSimpleName() + ": "
                + detail.substring(0, Math.min(240, detail.length()));
    }

    private static final class KeyMaterial {
        final PrivateKey privateKey;
        final PublicKey publicKey;
        final String fingerprint;
        KeyMaterial(PrivateKey privateKey, PublicKey publicKey, String fingerprint) {
            this.privateKey = privateKey;
            this.publicKey = publicKey;
            this.fingerprint = fingerprint;
        }
    }
}
