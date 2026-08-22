# CLASSIFIRE Offline Android Admission Signer

This Android app provides an offline, human-approved P-256 signing boundary for
CLASSIFIRE adjudicated admission manifests. It has no Internet permission and
cannot register an admission, submit canonical data, or create a Physical Model
Lock. Both signer screens block screenshots and recent-app previews.

The default screen:

1. imports a local v2 admission-manifest JSON file through a local-only Android document
   picker;
2. validates the exact schema, identifiers, hashes, issuer/key binding, maximum
   15-minute lifetime, expiry, matching secure-hardware-backed key, and stored
   public-key fingerprint;
3. displays all signed bindings for human review;
4. canonicalises the unsigned JSON exactly as the CLASSIFIRE verifier does;
5. requires strong biometric approval for `SHA256withECDSA`;
6. converts the result to strict low-S DER, verifies it locally, and lets the
   operator export the signed JSON through Android's document picker.

Key provisioning and the temporary device proof remain on a separate screen.
Opening that screen does not create a key. Persistent key creation still
requires explicit operational authority and a separate on-device confirmation.
The private key is never exportable; only its DER SubjectPublicKeyInfo and
SHA-256 fingerprint are displayed.
On Android 12 and later, signing accepts only Trusted Environment or StrongBox
keys; unsupported, software, and unknown levels are rejected. Android 11 retains
its platform hardware-backed check as a fail-closed compatibility path.

## Local verification

The app module targets Java 17. With JDK 21 and Android SDK 36 configured, and dependencies already present in
the local Gradle cache:

```powershell
.\gradlew.bat --offline --no-daemon clean testDebugUnitTest assembleDebug lintDebug
```

The unit tests cover manifest contract rejection, a shared Java/Python
canonical signing-byte vector, the 15-minute and expiry gates,
duplicate/unknown fields, malformed exported signature encoding, and strict low-S
DER normalisation. They are pure JVM tests: they do not access Android Keystore,
create a key, or produce an admission signature.

## Branding and release boundary

The launcher uses the approved, unchanged CLASSIFIRE master artwork imported
from reviewed commit `c3749fe`. The Android treatment centres that artwork on a
square canvas without cropping, recolouring, or changing its aspect ratio; the
original file's SHA-256 is protected by a regression test.

The build now has no application-icon lint warning. A signed distributable APK
still requires a separately controlled release-signing certificate. This is not
the Android Keystore P-256 device key: creating either key, signing an
admission, registering an admission, submitting canonical data, or locking data
remains a distinct operational decision.