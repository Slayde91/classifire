# CLASSIFIRE Android Signer Proof

This is a test-only proof that an Android device can create a non-exportable
P-256 Android Keystore key and perform a biometric-gated `SHA256withECDSA`
signature over a fixed local challenge.

It never receives CLASSIFIRE data, creates an admission, contacts a network
service, exports a private key, or changes CLASSIFIRE configuration. Each
successful proof deletes its temporary Keystore key before reporting success.

The production-key screen requires the approved issuer and Key ID at runtime,
then asks for a separate on-device confirmation before creating a persistent
P-256 signing key. It displays the public verification key as unpadded
base64url DER SubjectPublicKeyInfo and its SHA-256 fingerprint. The private
key remains non-exportable in Android Keystore.

Admission signing is not implemented in this app yet and still requires a
separate reviewed implementation and authorization.
