package au.com.classifire.admissionsigner;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.Arrays;
import java.util.Base64;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.UUID;
import java.util.regex.Pattern;

/** Pure-Java, fail-closed codec for the CLASSIFIRE admission-manifest v2 contract. */
final class AdmissionManifest {
    static final int MAX_BYTES = 128 * 1024;
    static final String SCHEMA = "CLASSIFIRE-ADJUDICATED-CANONICALISATION-ADMISSION-v2";
    static final String PURPOSE = "initial_adjudicated_canonicalisation";
    static final String ALGORITHM = "ECDSA_P256_SHA256";
    private static final Duration MAX_LIFETIME = Duration.ofMinutes(15);
    private static final Pattern IDENTIFIER = Pattern.compile("^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,159}$");
    private static final Pattern SHA256 = Pattern.compile("^[0-9A-F]{64}$");
    private static final Pattern BASE64URL = Pattern.compile("^[A-Za-z0-9_-]+$");
    private static final Pattern TIMESTAMP = Pattern.compile("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$");
    private static final Set<String> FIELDS = Collections.unmodifiableSet(new LinkedHashSet<>(Arrays.asList(
            "schema", "admission_id", "purpose", "project_id", "estimate_id", "source_run_id",
            "adjudicated_run_id", "preflight_receipt_sha256", "normalised_submission_payload_sha256",
            "protected_state_fingerprint", "protected_state_fingerprint_version", "artifact_digests",
            "policy_versions", "issuer", "key_id", "issued_at", "expires_at", "signature_algorithm",
            "signature")));

    private final TreeMap<String, Object> values;
    private final Instant issuedAt;
    private final Instant expiresAt;

    private AdmissionManifest(TreeMap<String, Object> values, Instant issuedAt, Instant expiresAt) {
        this.values = values;
        this.issuedAt = issuedAt;
        this.expiresAt = expiresAt;
    }

    static AdmissionManifest parse(byte[] json, Instant now) {
        if (json == null || json.length == 0 || json.length > MAX_BYTES) {
            throw new IllegalArgumentException("Manifest must be between 1 byte and 128 KiB");
        }
        String text = new String(json, StandardCharsets.UTF_8);
        if (!Arrays.equals(text.getBytes(StandardCharsets.UTF_8), json)) {
            throw new IllegalArgumentException("Manifest is not canonical UTF-8 text");
        }
        Object parsed = new JsonParser(text).parse();
        if (!(parsed instanceof Map)) throw new IllegalArgumentException("Manifest must be a JSON object");
        TreeMap<String, Object> values = copyObject(parsed);
        if (!values.keySet().equals(FIELDS)) throw new IllegalArgumentException("Manifest fields do not match v2");
        requireEqual(values, "schema", SCHEMA);
        requireEqual(values, "purpose", PURPOSE);
        requireEqual(values, "signature_algorithm", ALGORITHM);
        requireUuid(values, "admission_id");
        requireUuid(values, "project_id");
        requireUuid(values, "estimate_id");
        for (String field : Arrays.asList("source_run_id", "adjudicated_run_id",
                "protected_state_fingerprint_version", "issuer", "key_id")) requireIdentifier(values, field);
        for (String field : Arrays.asList("preflight_receipt_sha256",
                "normalised_submission_payload_sha256", "protected_state_fingerprint")) requireSha(values, field);
        requireStringMap(values, "artifact_digests", true);
        requireStringMap(values, "policy_versions", false);
        String signature = requireString(values, "signature");
        if (!isBase64url(signature)) throw new IllegalArgumentException("Invalid signature placeholder");
        Instant issuedAt = requireInstant(values, "issued_at");
        Instant expiresAt = requireInstant(values, "expires_at");
        Duration lifetime = Duration.between(issuedAt, expiresAt);
        if (lifetime.isZero() || lifetime.isNegative() || lifetime.compareTo(MAX_LIFETIME) > 0) {
            throw new IllegalArgumentException("Admission lifetime must be no more than 15 minutes");
        }
        if (issuedAt.isAfter(now)) throw new IllegalArgumentException("Admission is not yet valid");
        if (!now.isBefore(expiresAt)) throw new IllegalArgumentException("Admission has expired");
        return new AdmissionManifest(values, issuedAt, expiresAt);
    }

    byte[] signingBytes() {
        TreeMap<String, Object> unsigned = new TreeMap<>(values);
        unsigned.remove("signature");
        return JsonWriter.write(unsigned).getBytes(StandardCharsets.UTF_8);
    }

    byte[] signedJson(String signature) {
        if (!isBase64url(signature)) throw new IllegalArgumentException("Invalid signature encoding");
        TreeMap<String, Object> signed = new TreeMap<>(values);
        signed.put("signature", signature);
        return (JsonWriter.write(signed) + "\n").getBytes(StandardCharsets.UTF_8);
    }

    String value(String key) { return (String) values.get(key); }
    Instant issuedAt() { return issuedAt; }
    Instant expiresAt() { return expiresAt; }
    @SuppressWarnings("unchecked") Map<String, String> stringMap(String key) { return (Map<String, String>) values.get(key); }

    private static void requireEqual(Map<String, Object> values, String key, String expected) {
        if (!expected.equals(values.get(key))) throw new IllegalArgumentException("Invalid " + key);
    }

    private static boolean isBase64url(String value) {
        if (value == null || !BASE64URL.matcher(value).matches()) return false;
        try {
            Base64.getUrlDecoder().decode(value);
            return true;
        } catch (IllegalArgumentException exception) {
            return false;
        }
    }

    private static String requireString(Map<String, Object> values, String key) {
        Object value = values.get(key);
        if (!(value instanceof String)) throw new IllegalArgumentException(key + " must be a string");
        return (String) value;
    }

    private static void requireUuid(Map<String, Object> values, String key) {
        String value = requireString(values, key);
        try {
            if (!UUID.fromString(value).toString().equals(value)) throw new IllegalArgumentException();
        } catch (IllegalArgumentException exception) {
            throw new IllegalArgumentException("Invalid " + key);
        }
    }

    private static void requireIdentifier(Map<String, Object> values, String key) {
        if (!IDENTIFIER.matcher(requireString(values, key)).matches()) throw new IllegalArgumentException("Invalid " + key);
    }

    private static void requireSha(Map<String, Object> values, String key) {
        if (!SHA256.matcher(requireString(values, key)).matches()) throw new IllegalArgumentException("Invalid " + key);
    }

    private static Instant requireInstant(Map<String, Object> values, String key) {
        String value = requireString(values, key);
        if (!TIMESTAMP.matcher(value).matches()) throw new IllegalArgumentException("Invalid " + key);
        try {
            return Instant.parse(value);
        } catch (DateTimeParseException exception) {
            throw new IllegalArgumentException("Invalid " + key);
        }
    }

    private static void requireStringMap(Map<String, Object> values, String key, boolean digests) {
        Object raw = values.get(key);
        if (!(raw instanceof Map) || ((Map<?, ?>) raw).isEmpty()) throw new IllegalArgumentException("Invalid " + key);
        for (Map.Entry<?, ?> entry : ((Map<?, ?>) raw).entrySet()) {
            if (!(entry.getKey() instanceof String) || !IDENTIFIER.matcher((String) entry.getKey()).matches()
                    || !(entry.getValue() instanceof String)) throw new IllegalArgumentException("Invalid " + key);
            Pattern expected = digests ? SHA256 : IDENTIFIER;
            if (!expected.matcher((String) entry.getValue()).matches()) throw new IllegalArgumentException("Invalid " + key);
        }
    }

    @SuppressWarnings("unchecked")
    private static TreeMap<String, Object> copyObject(Object value) {
        TreeMap<String, Object> result = new TreeMap<>();
        for (Map.Entry<String, Object> entry : ((Map<String, Object>) value).entrySet()) {
            Object child = entry.getValue();
            result.put(entry.getKey(), child instanceof Map ? copyObject(child) : child);
        }
        return result;
    }

    private static final class JsonParser {
        private final String text;
        private int index;
        JsonParser(String text) { this.text = text; }
        Object parse() {
            skip();
            Object value = object();
            skip();
            if (index != text.length()) fail();
            return value;
        }
        private Map<String, Object> object() {
            expect('{');
            TreeMap<String, Object> result = new TreeMap<>();
            skip();
            if (take('}')) return result;
            while (true) {
                skip();
                String key = string();
                if (result.containsKey(key)) throw new IllegalArgumentException("Duplicate JSON key");
                skip(); expect(':'); skip();
                Object value = peek() == '{' ? object() : string();
                result.put(key, value);
                skip();
                if (take('}')) return result;
                expect(',');
            }
        }
        private String string() {
            expect('"');
            StringBuilder out = new StringBuilder();
            while (index < text.length()) {
                char c = text.charAt(index++);
                if (c == '"') return out.toString();
                if (c < 0x20) fail();
                if (c != '\\') { out.append(c); continue; }
                if (index >= text.length()) fail();
                char escaped = text.charAt(index++);
                switch (escaped) {
                    case '"': case '\\': case '/': out.append(escaped); break;
                    case 'b': out.append('\b'); break;
                    case 'f': out.append('\f'); break;
                    case 'n': out.append('\n'); break;
                    case 'r': out.append('\r'); break;
                    case 't': out.append('\t'); break;
                    case 'u':
                        if (index + 4 > text.length()) fail();
                        try { out.append((char) Integer.parseInt(text.substring(index, index + 4), 16)); }
                        catch (NumberFormatException exception) { fail(); }
                        index += 4;
                        break;
                    default: fail();
                }
            }
            fail(); return "";
        }
        private char peek() { if (index >= text.length()) fail(); return text.charAt(index); }
        private void skip() { while (index < text.length() && Character.isWhitespace(text.charAt(index))) index++; }
        private boolean take(char c) { if (index < text.length() && text.charAt(index) == c) { index++; return true; } return false; }
        private void expect(char c) { if (!take(c)) fail(); }
        private static void fail() { throw new IllegalArgumentException("Invalid JSON manifest"); }
    }

    private static final class JsonWriter {
        static String write(Map<String, Object> value) {
            StringBuilder out = new StringBuilder();
            appendObject(out, value);
            return out.toString();
        }
        @SuppressWarnings("unchecked")
        private static void appendObject(StringBuilder out, Map<String, Object> value) {
            out.append('{');
            boolean first = true;
            for (Map.Entry<String, Object> entry : new TreeMap<>(value).entrySet()) {
                if (!first) out.append(',');
                first = false;
                appendString(out, entry.getKey()); out.append(':');
                if (entry.getValue() instanceof Map) appendObject(out, (Map<String, Object>) entry.getValue());
                else appendString(out, (String) entry.getValue());
            }
            out.append('}');
        }
        private static void appendString(StringBuilder out, String value) {
            out.append('"');
            for (int i = 0; i < value.length(); i++) {
                char c = value.charAt(i);
                switch (c) {
                    case '"': out.append("\\\""); break;
                    case '\\': out.append("\\\\"); break;
                    case '\b': out.append("\\b"); break;
                    case '\f': out.append("\\f"); break;
                    case '\n': out.append("\\n"); break;
                    case '\r': out.append("\\r"); break;
                    case '\t': out.append("\\t"); break;
                    default:
                        if (c < 0x20) out.append(String.format("\\u%04x", (int) c)); else out.append(c);
                }
            }
            out.append('"');
        }
    }
}
