package au.com.classifire.admissionsigner;

import java.math.BigInteger;
import java.security.PublicKey;
import java.security.Signature;

final class P256Signatures {
    private static final BigInteger ORDER = new BigInteger(
            "FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551", 16);

    private P256Signatures() {}

    static byte[] canonicalLowS(byte[] der) {
        int[] offset = {0};
        if (read(der, offset) != 0x30) fail();
        int sequenceLength = readLength(der, offset);
        if (sequenceLength != der.length - offset[0]) fail();
        BigInteger r = readInteger(der, offset);
        BigInteger s = readInteger(der, offset);
        if (offset[0] != der.length || r.signum() <= 0 || r.compareTo(ORDER) >= 0
                || s.signum() <= 0 || s.compareTo(ORDER) >= 0) fail();
        if (s.compareTo(ORDER.shiftRight(1)) > 0) s = ORDER.subtract(s);
        byte[] rb = positive(r);
        byte[] sb = positive(s);
        int bodyLength = 4 + rb.length + sb.length;
        byte[] result = new byte[2 + bodyLength];
        int p = 0;
        result[p++] = 0x30; result[p++] = (byte) bodyLength;
        result[p++] = 0x02; result[p++] = (byte) rb.length;
        System.arraycopy(rb, 0, result, p, rb.length); p += rb.length;
        result[p++] = 0x02; result[p++] = (byte) sb.length;
        System.arraycopy(sb, 0, result, p, sb.length);
        return result;
    }

    static boolean verifies(byte[] signingBytes, byte[] derSignature, PublicKey publicKey) throws Exception {
        Signature verifier = Signature.getInstance("SHA256withECDSA");
        verifier.initVerify(publicKey);
        verifier.update(signingBytes);
        return verifier.verify(derSignature);
    }

    private static BigInteger readInteger(byte[] der, int[] offset) {
        if (read(der, offset) != 0x02) fail();
        int length = readLength(der, offset);
        if (length == 0 || offset[0] + length > der.length) fail();
        byte[] value = new byte[length];
        System.arraycopy(der, offset[0], value, 0, length);
        offset[0] += length;
        if ((value[0] & 0x80) != 0 || (length > 1 && value[0] == 0 && (value[1] & 0x80) == 0)) fail();
        return new BigInteger(value);
    }

    private static int readLength(byte[] der, int[] offset) {
        int value = read(der, offset);
        if ((value & 0x80) != 0) fail();
        return value;
    }

    private static int read(byte[] der, int[] offset) {
        if (der == null || offset[0] >= der.length) fail();
        return der[offset[0]++] & 0xff;
    }

    private static byte[] positive(BigInteger value) { return value.toByteArray(); }
    private static void fail() { throw new IllegalArgumentException("Invalid strict DER P-256 signature"); }
}
