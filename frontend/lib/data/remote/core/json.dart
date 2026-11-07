library;

import '../../errors.dart';

const badResponse = 'BAD_RESPONSE';

Map<String, Object?> asJsonMap(Object? value, [String what = 'response']) {
  if (value is Map<String, Object?>) return value;
  throw _wrong(what, 'an object', value);
}

List<Object?> asJsonList(Object? value, [String what = 'response']) {
  if (value is List<Object?>) return value;
  throw _wrong(what, 'an array', value);
}

String readString(Map<String, Object?> json, String key) =>
    _read<String>(json, key, 'a string');

String? readStringOrNull(Map<String, Object?> json, String key) =>
    _readOrNull<String>(json, key, 'a string');

int readInt(Map<String, Object?> json, String key) =>
    readIntOrNull(json, key) ?? (throw _missing(key));

int? readIntOrNull(Map<String, Object?> json, String key) {
  final value = json[key];
  if (value == null) return null;
  if (value is int) return value;
  if (value is double && value == value.truncateToDouble()) {
    return value.toInt();
  }
  throw _wrong(key, 'an integer', value);
}

double readDouble(Map<String, Object?> json, String key) =>
    readDoubleOrNull(json, key) ?? (throw _missing(key));

double? readDoubleOrNull(Map<String, Object?> json, String key) =>
    _readOrNull<num>(json, key, 'a number')?.toDouble();

bool readBool(Map<String, Object?> json, String key) =>
    _read<bool>(json, key, 'a boolean');

bool? readBoolOrNull(Map<String, Object?> json, String key) =>
    _readOrNull<bool>(json, key, 'a boolean');

DateTime readDateTime(Map<String, Object?> json, String key) =>
    readDateTimeOrNull(json, key) ?? (throw _missing(key));

DateTime? readDateTimeOrNull(Map<String, Object?> json, String key) {
  final text = _readOrNull<String>(json, key, 'an ISO-8601 time');
  if (text == null) return null;
  return tryParseServerTime(text) ??
      (throw _wrong(key, 'an ISO-8601 time', text));
}

Map<String, Object?> readMap(Map<String, Object?> json, String key) =>
    _read<Map<String, Object?>>(json, key, 'an object');

Map<String, Object?>? readMapOrNull(Map<String, Object?> json, String key) =>
    _readOrNull<Map<String, Object?>>(json, key, 'an object');

List<Object?> readList(Map<String, Object?> json, String key) =>
    _read<List<Object?>>(json, key, 'an array');

List<String> readStringList(Map<String, Object?> json, String key) => [
  for (final (i, item) in readList(json, key).indexed)
    if (item is String) item else throw _wrong('$key[$i]', 'a string', item),
];

List<T> readObjectList<T>(
  Map<String, Object?> json,
  String key,
  T Function(Map<String, Object?> item) parse,
) => [
  for (final (i, item) in readList(json, key).indexed)
    parse(asJsonMap(item, '$key[$i]')),
];

DateTime parseServerTime(String text) =>
    tryParseServerTime(text) ??
    (throw ServerException(
      code: badResponse,
      message: 'Expected an ISO-8601 time, got "$text"',
    ));

DateTime? tryParseServerTime(String? text) {
  if (text == null) return null;
  final trimmed = text.trim();
  final zoned = _hasZone.hasMatch(trimmed) ? trimmed : '${trimmed}Z';
  return DateTime.tryParse(zoned)?.toLocal();
}

final _hasZone = RegExp(r'(Z|[+-]\d{2}:?\d{2})$', caseSensitive: false);

String displayPhone(String phone) =>
    phone.startsWith('+84') ? '0${phone.substring(3)}' : phone;

T _read<T extends Object>(
  Map<String, Object?> json,
  String key,
  String expected,
) => _readOrNull<T>(json, key, expected) ?? (throw _missing(key));

T? _readOrNull<T extends Object>(
  Map<String, Object?> json,
  String key,
  String expected,
) {
  final value = json[key];
  if (value == null || value is T) return value as T?;
  throw _wrong(key, expected, value);
}

ServerException _missing(String key) =>
    ServerException(code: badResponse, message: 'Missing field "$key"');

ServerException _wrong(String what, String expected, Object? value) =>
    ServerException(
      code: badResponse,
      message: '"$what": expected $expected, got ${value.runtimeType}',
    );
