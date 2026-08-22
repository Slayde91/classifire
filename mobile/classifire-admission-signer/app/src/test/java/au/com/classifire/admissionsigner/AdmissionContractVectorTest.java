package au.com.classifire.admissionsigner;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.time.Instant;
import org.junit.Test;

public final class AdmissionContractVectorTest {
    @Test
    public void sharedVectorMatchesCanonicalSigningBytes() throws Exception {
        byte[] manifestBytes = resource("admission-manifest-v2-input.json");
        byte[] expected = trimFinalLineEnding(
                resource("admission-manifest-v2-signing-canonical.json"));

        AdmissionManifest manifest = AdmissionManifest.parse(
                manifestBytes, Instant.parse("2026-08-22T01:01:00Z"));

        assertArrayEquals(expected, manifest.signingBytes());
        assertEquals("classifire-governance", manifest.value("issuer"));
        assertEquals("governance-p256-01", manifest.value("key_id"));
    }

    private static byte[] resource(String name) throws Exception {
        try (InputStream input = AdmissionContractVectorTest.class
                .getClassLoader().getResourceAsStream(name)) {
            if (input == null) throw new IllegalStateException("Missing test resource: " + name);
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            byte[] buffer = new byte[4096];
            int count;
            while ((count = input.read(buffer)) != -1) output.write(buffer, 0, count);
            return output.toByteArray();
        }
    }

    private static byte[] trimFinalLineEnding(byte[] value) {
        int length = value.length;
        if (length > 0 && value[length - 1] == '\n') length--;
        if (length > 0 && value[length - 1] == '\r') length--;
        byte[] result = new byte[length];
        System.arraycopy(value, 0, result, 0, length);
        return result;
    }
}
