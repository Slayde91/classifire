package au.com.classifire.admissionsigner;

import static org.junit.Assert.assertArrayEquals;

import org.junit.Test;

public final class P256SignaturesTest {
    @Test
    public void convertsHighSToStrictCanonicalLowS() {
        byte[] highS = hex("3026020101022100FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632550");
        assertArrayEquals(hex("3006020101020101"), P256Signatures.canonicalLowS(highS));
    }

    @Test(expected = IllegalArgumentException.class)
    public void rejectsNonMinimalDer() {
        P256Signatures.canonicalLowS(hex("300702020001020101"));
    }

    private static byte[] hex(String value) {
        byte[] result = new byte[value.length() / 2];
        for (int i = 0; i < result.length; i++) {
            result[i] = (byte) Integer.parseInt(value.substring(i * 2, i * 2 + 2), 16);
        }
        return result;
    }
}
