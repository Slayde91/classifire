package au.com.classifire.admissionsigner;

import android.app.Activity;
import android.app.AlertDialog;
import android.hardware.biometrics.BiometricManager;
import android.hardware.biometrics.BiometricPrompt;
import android.os.Bundle;
import android.os.CancellationSignal;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyInfo;
import android.security.keystore.KeyProperties;
import android.view.Gravity;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.KeyPairGenerator;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.Signature;
import java.security.spec.ECGenParameterSpec;
import java.util.Base64;
import java.util.concurrent.Executor;
import java.util.regex.Pattern;

public final class MainActivity extends Activity {
    private static final String TEST_ALIAS = "classifire_admission_p256_test_v1";
    private static final String PRODUCTION_ALIAS_PREFIX = "classifire_admission_p256_production_";
    private static final Pattern IDENTIFIER = Pattern.compile("^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,159}$");
    private static final byte[] CHALLENGE =
            "CLASSIFIRE Android P-256 signer proof v1".getBytes(StandardCharsets.UTF_8);
    private static final BigInteger P256_ORDER = new BigInteger(
            "FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551", 16);

    private TextView status;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        ScrollView scroll = new ScrollView(this);
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setGravity(Gravity.CENTER);
        int padding = 48;
        layout.setPadding(padding, padding, padding, padding);

        TextView title = new TextView(this);
        title.setText(R.string.proof_title);
        title.setTextSize(22);
        layout.addView(title);

        status = new TextView(this);
        status.setText(R.string.proof_initial_status);
        status.setPadding(0, 32, 0, 32);
        status.setTextIsSelectable(true);
        layout.addView(status);

        Button proof = new Button(this);
        proof.setText(R.string.proof_button);
        proof.setOnClickListener(view -> beginProof());
        layout.addView(proof);

        TextView productionTitle = new TextView(this);
        productionTitle.setText(R.string.production_key_title);
        productionTitle.setTextSize(20);
        productionTitle.setPadding(0, 48, 0, 12);
        layout.addView(productionTitle);

        TextView productionNotice = new TextView(this);
        productionNotice.setText(R.string.production_key_notice);
        layout.addView(productionNotice);

        EditText issuerInput = new EditText(this);
        issuerInput.setHint(R.string.issuer_hint);
        issuerInput.setSingleLine(true);
        layout.addView(issuerInput);

        EditText keyIdInput = new EditText(this);
        keyIdInput.setHint(R.string.key_id_hint);
        keyIdInput.setSingleLine(true);
        layout.addView(keyIdInput);

        EditText custodianInput = new EditText(this);
        custodianInput.setHint(R.string.custodian_hint);
        custodianInput.setSingleLine(true);
        layout.addView(custodianInput);

        Button production = new Button(this);
        production.setText(R.string.create_production_key_button);
        production.setOnClickListener(view -> confirmProductionKey(
                issuerInput.getText().toString().trim(), keyIdInput.getText().toString().trim(),
                custodianInput.getText().toString().trim()));
        layout.addView(production);
        scroll.addView(layout);
        setContentView(scroll);
    }

    private void confirmProductionKey(String issuer, String keyId, String custodian) {
        if (!IDENTIFIER.matcher(issuer).matches() || !IDENTIFIER.matcher(keyId).matches()
                || custodian.isBlank() || custodian.length() > 160) {
            status.setText(R.string.production_setup_rejected_fields);
            return;
        }
        new AlertDialog.Builder(this)
                .setTitle(R.string.production_key_confirmation_title)
                .setMessage(getString(R.string.production_key_confirmation, issuer, keyId, custodian))
                .setNegativeButton(R.string.cancel, null)
                .setPositiveButton(R.string.create_key, (dialog, which) -> createProductionKey(issuer, keyId, custodian))
                .show();
    }

    private void createProductionKey(String issuer, String keyId, String custodian) {
        String alias = PRODUCTION_ALIAS_PREFIX + keyId;
        try {
            KeyStore store = keyStore();
            if (store.containsAlias(alias)) {
                status.setText(R.string.production_key_exists);
                return;
            }
            KeyPairGenerator generator = KeyPairGenerator.getInstance(
                    KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore");
            generator.initialize(new KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_SIGN)
                    .setAlgorithmParameterSpec(new ECGenParameterSpec("secp256r1"))
                    .setDigests(KeyProperties.DIGEST_SHA256)
                    .setUserAuthenticationRequired(true)
                    .setUserAuthenticationParameters(0, KeyProperties.AUTH_BIOMETRIC_STRONG)
                    .build());
            generator.generateKeyPair();

            PrivateKey privateKey = (PrivateKey) store.getKey(alias, null);
            KeyInfo keyInfo = KeyFactory.getInstance(privateKey.getAlgorithm(), "AndroidKeyStore")
                    .getKeySpec(privateKey, KeyInfo.class);
            if (!KeystoreSecurity.isHardwareBacked(keyInfo)) {
                store.deleteEntry(alias);
                throw new SecurityException("Android Keystore did not report secure-hardware backing");
            }
            byte[] publicKeyDer = store.getCertificate(alias).getPublicKey().getEncoded();
            String publicKey = Base64.getUrlEncoder().withoutPadding().encodeToString(publicKeyDer);
            String fingerprint = Base64.getUrlEncoder().withoutPadding().encodeToString(
                    MessageDigest.getInstance("SHA-256").digest(publicKeyDer));
            getSharedPreferences("classifire_admission_signer", MODE_PRIVATE).edit()
                    .putString("production_issuer_" + keyId, issuer)
                    .putString("production_custodian_" + keyId, custodian)
                    .putString("production_fingerprint_" + keyId, fingerprint)
                    .apply();
            status.setText(getString(R.string.production_key_created, issuer, keyId, custodian,
                    publicKey, fingerprint));
        } catch (Exception exception) {
            status.setText(getString(R.string.production_key_setup_failed, safeFailure(exception)));
        }
    }

    private void beginProof() {
        try {
            deleteTestKey();
            KeyPairGenerator generator = KeyPairGenerator.getInstance(
                    KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore");
            generator.initialize(new KeyGenParameterSpec.Builder(
                    TEST_ALIAS, KeyProperties.PURPOSE_SIGN | KeyProperties.PURPOSE_VERIFY)
                    .setAlgorithmParameterSpec(new ECGenParameterSpec("secp256r1"))
                    .setDigests(KeyProperties.DIGEST_SHA256)
                    .setUserAuthenticationRequired(true)
                    .setUserAuthenticationParameters(
                            0, KeyProperties.AUTH_BIOMETRIC_STRONG)
                    .build());
            generator.generateKeyPair();

            PrivateKey privateKey = (PrivateKey) keyStore().getKey(TEST_ALIAS, null);
            Signature signature = Signature.getInstance("SHA256withECDSA");
            signature.initSign(privateKey);
            authenticateAndSign(signature);
        } catch (Exception exception) {
            deleteTestKey();
            status.setText(getString(R.string.proof_setup_failed, safeFailure(exception)));
        }
    }

    private void authenticateAndSign(Signature signature) {
        Executor executor = getMainExecutor();
        BiometricPrompt prompt = new BiometricPrompt.Builder(this)
                .setTitle(getString(R.string.proof_biometric_title))
                .setSubtitle(getString(R.string.proof_biometric_subtitle))
                .setAllowedAuthenticators(BiometricManager.Authenticators.BIOMETRIC_STRONG)
                .build();
        prompt.authenticate(new BiometricPrompt.CryptoObject(signature), new CancellationSignal(), executor,
                new BiometricPrompt.AuthenticationCallback() {
                    @Override
                    public void onAuthenticationError(int errorCode, CharSequence error) {
                        deleteTestKey();
                        status.setText(R.string.proof_cancelled);
                    }

                    @Override
                    public void onAuthenticationSucceeded(
                            BiometricPrompt.AuthenticationResult result) {
                        try {
                            Signature approved = result.getCryptoObject().getSignature();
                            approved.update(CHALLENGE);
                            canonicalLowS(approved.sign());
                            String fingerprint = publicKeyFingerprint();
                            deleteTestKey();
                            status.setText(getString(R.string.proof_passed, fingerprint));
                        } catch (Exception exception) {
                            deleteTestKey();
                            status.setText(getString(R.string.proof_signing_failed,
                                    safeFailure(exception)));
                        }
                    }
                });
    }

    private String publicKeyFingerprint() throws Exception {
        byte[] encoded = keyStore().getCertificate(TEST_ALIAS).getPublicKey().getEncoded();
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(encoded);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(digest);
    }

    private static byte[] canonicalLowS(byte[] derSignature) {
        int offset = 0;
        if (derSignature[offset++] != 0x30) throw new IllegalArgumentException("Invalid DER sequence");
        int length = derSignature[offset++] & 0xff;
        if (length != derSignature.length - 2) throw new IllegalArgumentException("Invalid DER length");
        if (derSignature[offset++] != 0x02) throw new IllegalArgumentException("Invalid DER R");
        int rLength = derSignature[offset++] & 0xff;
        BigInteger r = new BigInteger(1, slice(derSignature, offset, rLength));
        offset += rLength;
        if (derSignature[offset++] != 0x02) throw new IllegalArgumentException("Invalid DER S");
        int sLength = derSignature[offset++] & 0xff;
        BigInteger s = new BigInteger(1, slice(derSignature, offset, sLength));
        if (offset + sLength != derSignature.length) throw new IllegalArgumentException("Invalid DER tail");
        if (s.compareTo(P256_ORDER.shiftRight(1)) > 0) s = P256_ORDER.subtract(s);
        byte[] rBytes = positive(r);
        byte[] sBytes = positive(s);
        byte[] result = new byte[6 + rBytes.length + sBytes.length];
        int index = 0;
        result[index++] = 0x30;
        result[index++] = (byte) (4 + rBytes.length + sBytes.length);
        result[index++] = 0x02;
        result[index++] = (byte) rBytes.length;
        System.arraycopy(rBytes, 0, result, index, rBytes.length);
        index += rBytes.length;
        result[index++] = 0x02;
        result[index++] = (byte) sBytes.length;
        System.arraycopy(sBytes, 0, result, index, sBytes.length);
        return result;
    }

    private static byte[] slice(byte[] value, int offset, int length) {
        byte[] result = new byte[length];
        System.arraycopy(value, offset, result, 0, length);
        return result;
    }

    private static byte[] positive(BigInteger value) {
        byte[] encoded = value.toByteArray();
        return encoded.length == 0 ? new byte[]{0} : encoded;
    }

    private static KeyStore keyStore() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        return store;
    }

    private static void deleteTestKey() {
        try {
            KeyStore store = keyStore();
            if (store.containsAlias(TEST_ALIAS)) store.deleteEntry(TEST_ALIAS);
        } catch (Exception ignored) {
            // Failing closed here means the app never reports a successful proof.
        }
    }

    private static String safeFailure(Exception exception) {
        String detail = exception.getMessage();
        if (detail == null || detail.isBlank()) return exception.getClass().getSimpleName();
        return exception.getClass().getSimpleName() + ": " + detail.substring(0, Math.min(240, detail.length()));
    }
}
