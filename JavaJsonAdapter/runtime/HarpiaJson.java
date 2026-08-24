// Ships verbatim into every Java-target build (see JavaJsonAdapter.py). Hand-
// written, NOT generated -- unlike the C++ target's JsonAdapter, which emits
// one thin wrapper header per message, this single class serves every
// message: protobuf-java's `Message`/`Message.Builder` are common interfaces
// every generated message class already implements, so `JsonFormat` is
// already generic -- there is nothing per-message left to generate. See
// JavaJsonAdapter/CLAUDE.md for the full reasoning.
package com.harpia.runtime.json;

import com.google.protobuf.InvalidProtocolBufferException;
import com.google.protobuf.Message;
import com.google.protobuf.util.JsonFormat;

public final class HarpiaJson {
    private HarpiaJson() {}

    // message -> JSON (spec 9 / 8.1)
    public static String toJson(Message msg) {
        try {
            return JsonFormat.printer().print(msg);
        } catch (InvalidProtocolBufferException e) {
            // Only thrown for a malformed Any payload -- unreachable for a
            // harpia-generated message, which never embeds Any.
            throw new IllegalStateException(e);
        }
    }

    // JSON -> message (spec 9 / 8.2). Ignores keys the schema doesn't
    // recognize (a newer peer's added field) so parsing degrades the way
    // proto3 binary/XML already do, rather than hard-erroring on exactly the
    // case forward-compatibility exists for -- see protoFile/CLAUDE.md's
    // `optional` note.
    public static <T extends Message.Builder> T fromJson(String json, T builder)
            throws InvalidProtocolBufferException {
        JsonFormat.parser().ignoringUnknownFields().merge(json, builder);
        return builder;
    }

    // Is `json` a valid message for `prototype`'s type? (same unknown-field
    // tolerance as fromJson). `prototype` is cloned internally, so the
    // caller's own builder is never mutated by a probe call -- pass e.g.
    // `SomeMessage.newBuilder()`.
    public static boolean isValidJson(String json, Message.Builder prototype) {
        try {
            fromJson(json, prototype.clone());
            return true;
        } catch (InvalidProtocolBufferException e) {
            return false;
        }
    }
}
