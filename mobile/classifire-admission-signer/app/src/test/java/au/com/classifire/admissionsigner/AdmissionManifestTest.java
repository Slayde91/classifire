package au.com.classifire.admissionsigner;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import org.junit.Test;

public final class AdmissionManifestTest {
    private static final Instant NOW = Instant.parse("2026-08-22T01:01:00Z");

    @Test
    public void canonicalSigningBytesMatchBackendJsonContract() {
        AdmissionManifest manifest = AdmissionManifest.parse(fixture().getBytes(StandardCharsets.UTF_8), NOW);
        String canonical = new String(manifest.signingBytes(), StandardCharsets.UTF_8);
        assertEquals("{\"adjudicated_run_id\":\"adjudicated-run-1\",\"admission_id\":\"11111111-1111-4111-8111-111111111111\","
                + "\"artifact_digests\":{\"a\":\"CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC\","
                + "\"z\":\"DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD\"},"
                + "\"estimate_id\":\"33333333-3333-4333-8333-333333333333\",\"expires_at\":\"2026-08-22T01:10:00Z\","
                + "\"issued_at\":\"2026-08-22T01:00:00Z\",\"issuer\":\"classifire-governance\","
                + "\"key_id\":\"governance-p256-01\",\"normalised_submission_payload_sha256\":"
                + "\"BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB\","
                + "\"policy_versions\":{\"physical_policy\":\"CLASSIFIRE-PHYSICAL-v1\"},"
                + "\"preflight_receipt_sha256\":\"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\","
                + "\"project_id\":\"22222222-2222-4222-8222-222222222222\",\"protected_state_fingerprint\":"
                + "\"EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE\","
                + "\"protected_state_fingerprint_version\":\"CLASSIFIRE-PROTECTED-STATE-v1\","
                + "\"purpose\":\"initial_adjudicated_canonicalisation\",\"schema\":"
                + "\"CLASSIFIRE-ADJUDICATED-CANONICALISATION-ADMISSION-v2\","
                + "\"signature_algorithm\":\"ECDSA_P256_SHA256\",\"source_run_id\":\"source-run-1\"}", canonical);
        assertTrue(new String(manifest.signedJson("AQ"), StandardCharsets.UTF_8)
                .contains("\"signature\":\"AQ\""));
    }

    @Test
    public void signedJsonRejectsMalformedSignatureEncoding() {
        AdmissionManifest manifest = AdmissionManifest.parse(fixture().getBytes(StandardCharsets.UTF_8), NOW);
        try {
            manifest.signedJson("A");
            fail("Expected invalid signature encoding rejection");
        } catch (IllegalArgumentException expected) {
            assertEquals("Invalid signature encoding", expected.getMessage());
        }
    }

    @Test
    public void rejectsExpiredOverlongUnknownAndDuplicateContracts() {
        rejected(fixture().replace("2026-08-22T01:10:00Z", "2026-08-22T01:01:00Z"), NOW);
        rejected(fixture().replace("2026-08-22T01:10:00Z", "2026-08-22T01:16:00Z"), NOW);
        rejected(fixture().replace("2026-08-22T01:00:00Z", "2026-08-22T01:02:00Z"), NOW);
        rejected(fixture().replace("2026-08-22T01:00:00Z", "2026-08-22T01:00:00+00:00"), NOW);
        rejected(fixture().replace("\"signature\":\"AA\"", "\"signature\":\"A\""), NOW);
        rejected(fixture().replace("\"signature\":\"AA\"", "\"extra\":\"x\",\"signature\":\"AA\""), NOW);
        rejected(fixture().replace("\"issuer\":\"classifire-governance\"",
                "\"issuer\":\"classifire-governance\",\"issuer\":\"other\""), NOW);
    }

    private static void rejected(String value, Instant now) {
        try {
            AdmissionManifest.parse(value.getBytes(StandardCharsets.UTF_8), now);
            fail("Expected manifest rejection");
        } catch (IllegalArgumentException expected) {
            assertTrue(expected.getMessage() != null);
        }
    }

    private static String fixture() {
        return "{"
                + "\"signature\":\"AA\",\"schema\":\"CLASSIFIRE-ADJUDICATED-CANONICALISATION-ADMISSION-v2\","
                + "\"admission_id\":\"11111111-1111-4111-8111-111111111111\","
                + "\"purpose\":\"initial_adjudicated_canonicalisation\","
                + "\"project_id\":\"22222222-2222-4222-8222-222222222222\","
                + "\"estimate_id\":\"33333333-3333-4333-8333-333333333333\","
                + "\"source_run_id\":\"source-run-1\",\"adjudicated_run_id\":\"adjudicated-run-1\","
                + "\"preflight_receipt_sha256\":\"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\","
                + "\"normalised_submission_payload_sha256\":\"BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB\","
                + "\"protected_state_fingerprint\":\"EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE\","
                + "\"protected_state_fingerprint_version\":\"CLASSIFIRE-PROTECTED-STATE-v1\","
                + "\"artifact_digests\":{\"z\":\"DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD\","
                + "\"a\":\"CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC\"},"
                + "\"policy_versions\":{\"physical_policy\":\"CLASSIFIRE-PHYSICAL-v1\"},"
                + "\"issuer\":\"classifire-governance\",\"key_id\":\"governance-p256-01\","
                + "\"issued_at\":\"2026-08-22T01:00:00Z\",\"expires_at\":\"2026-08-22T01:10:00Z\","
                + "\"signature_algorithm\":\"ECDSA_P256_SHA256\"}";
    }
}
