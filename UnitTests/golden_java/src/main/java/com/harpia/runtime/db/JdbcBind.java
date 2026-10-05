// Ships verbatim into every Java-target build (see JavaDbAdapter.py). Hand-
// written, NOT generated -- the structural analogue of SOCI's use()/into()
// (Database/CLAUDE.md), but reflection-based rather than a set of typed
// per-column-kind calls: protobuf-java's Descriptors.FieldDescriptor lets a
// field be looked up by its EXACT .proto name (Message.getDescriptorForType()
// .findFieldByName(...)) and read/written generically via
// Message.getField(fd)/Builder.setField(fd, value) -- so generated DAO code
// (JavaDatabase/JavaCrudlAdapter.py) never needs to predict protoc's
// camelCase Java accessor name for a field (a real, otherwise-unverifiable
// risk without a JDK/protoc on the harpia generation host -- see
// JavaDatabase/CLAUDE.md).
package com.harpia.runtime.db;

import com.google.protobuf.Descriptors.EnumValueDescriptor;
import com.google.protobuf.Descriptors.FieldDescriptor;
import com.google.protobuf.Message;
import com.google.protobuf.MessageOrBuilder;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class JdbcBind {
    private JdbcBind() {}

    // Bind field `fieldName` of `msg` into `ps` at 1-based `index`,
    // dispatching on the field's own protobuf type.
    public static void bind(PreparedStatement ps, int index, Message msg, String fieldName)
            throws SQLException {
        FieldDescriptor fd = fieldFor(msg, fieldName);
        Object value = msg.getField(fd);
        switch (fd.getJavaType()) {
            case INT:
                ps.setInt(index, (Integer) value);
                break;
            case LONG:
                ps.setLong(index, (Long) value);
                break;
            case FLOAT:
                ps.setFloat(index, (Float) value);
                break;
            case DOUBLE:
                ps.setDouble(index, (Double) value);
                break;
            case STRING:
                ps.setString(index, (String) value);
                break;
            case ENUM:
                ps.setInt(index, ((EnumValueDescriptor) value).getNumber());
                break;
            default:
                throw new IllegalArgumentException(
                    "JdbcBind.bind: unsupported field type " + fd.getJavaType()
                    + " for field " + fieldName);
        }
    }

    // Extract column `columnLabel` from `rs` into field `fieldName` on
    // `builder`. A SQL NULL (e.g. a column a C++/Python migration added to a
    // pre-existing row) sets the field's default value -- ""/0/the first
    // enum value -- exactly as the C++ (indicator-guarded) and Python DAOs
    // do; setField(fd, null) used to throw (java-jdbc-null-text-DEFECT).
    public static void extract(ResultSet rs, String columnLabel, Message.Builder builder,
                               String fieldName) throws SQLException {
        FieldDescriptor fd = fieldFor(builder, fieldName);
        Object value;
        switch (fd.getJavaType()) {
            case INT:
                value = rs.getInt(columnLabel);
                break;
            case LONG:
                value = rs.getLong(columnLabel);
                break;
            case FLOAT:
                value = rs.getFloat(columnLabel);
                break;
            case DOUBLE:
                value = rs.getDouble(columnLabel);
                break;
            case STRING:
                value = rs.getString(columnLabel);
                break;
            case ENUM:
                int number = rs.getInt(columnLabel);
                if (rs.wasNull()) {
                    value = null;
                    break;
                }
                EnumValueDescriptor evd = fd.getEnumType().findValueByNumber(number);
                if (evd == null) {
                    throw new IllegalArgumentException(
                        "JdbcBind.extract: unrecognized enum value " + number
                        + " for field " + fieldName);
                }
                value = evd;
                break;
            default:
                throw new IllegalArgumentException(
                    "JdbcBind.extract: unsupported field type " + fd.getJavaType()
                    + " for field " + fieldName);
        }
        if (rs.wasNull()) {
            value = fd.getDefaultValue();
        }
        builder.setField(fd, value);
    }

    private static FieldDescriptor fieldFor(MessageOrBuilder msgOrBuilder, String fieldName) {
        FieldDescriptor fd = msgOrBuilder.getDescriptorForType().findFieldByName(fieldName);
        if (fd == null) {
            throw new IllegalArgumentException("JdbcBind: no such field: " + fieldName);
        }
        return fd;
    }
}
