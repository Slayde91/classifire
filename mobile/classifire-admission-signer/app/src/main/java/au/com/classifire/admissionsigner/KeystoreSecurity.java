package au.com.classifire.admissionsigner;

import android.os.Build;
import android.security.keystore.KeyInfo;
import android.security.keystore.KeyProperties;

/** Fail-closed Android Keystore hardware-security check across API 30 and later. */
final class KeystoreSecurity {
    private KeystoreSecurity() {}

    static boolean isHardwareBacked(KeyInfo keyInfo) {
        if (keyInfo == null) return false;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            int level = keyInfo.getSecurityLevel();
            return level == KeyProperties.SECURITY_LEVEL_TRUSTED_ENVIRONMENT
                    || level == KeyProperties.SECURITY_LEVEL_STRONGBOX;
        }
        return legacyIsHardwareBacked(keyInfo);
    }

    @SuppressWarnings("deprecation")
    private static boolean legacyIsHardwareBacked(KeyInfo keyInfo) {
        return keyInfo.isInsideSecureHardware();
    }
}
