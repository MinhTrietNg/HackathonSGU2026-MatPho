library;

import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mat_pho/data/remote/core/api_client.dart';

import '../../fakes/remote_doubles.dart';

final class GroupCameraServer {
  final requests = <http.Request>[];
  final _replies = <String, (int, Object?)>{};

  void on(String method, String path, Object? json, {int status = 200}) =>
      _replies['$method $path'] = (status, json);

  void fail(
    String method,
    String path,
    int status,
    String code, [
    Map<String, Object?> details = const {},
  ]) => on(method, path, {
    'error': {'code': code, 'message': code, 'details': details},
  }, status: status);

  late final ApiClient api = ApiClient(
    config: testApiConfig,
    tokens: FakeAuthTokenSource(token: 'tok-1'),
    httpClient: MockClient((request) async {
      requests.add(request);
      final path = request.url.path.replaceFirst('/api/v1', '');
      final reply = _replies['${request.method} $path'];
      if (reply == null) {
        return _json({
          'error': {'code': 'NOT_FOUND', 'message': 'no route', 'details': {}},
        }, 404);
      }
      return _json(reply.$2, reply.$1);
    }),
  );

  http.Request request(String method, String path) => requests.singleWhere(
    (r) => r.method == method && r.url.path.replaceFirst('/api/v1', '') == path,
  );

  Object? body(String method, String path) =>
      jsonDecode(request(method, path).body);

  List<String> get calls => [
    for (final r in requests)
      '${r.method} ${r.url.path.replaceFirst('/api/v1', '')}',
  ];

  static http.Response _json(Object? json, int status) => http.Response.bytes(
    utf8.encode(jsonEncode(json)),
    status,
    headers: {'content-type': 'application/json'},
  );
}

const personalGroupJson = {
  'group_id': 'grp_personal_usr_me',
  'group_name': 'Cá Nhân',
  'is_personal': true,
  'address': null,
  'member_count': 1,
  'camera_count': 0,
  'my_role': 'LEADER',
  'my_nickname': 'Tôi',
};

const skyGroupJson = {
  'group_id': 'grp_sky_garden_01',
  'group_name': 'Chung cư Sky Garden',
  'is_personal': false,
  'address': '12 Nguyễn Văn Linh, Q.7, TP.HCM',
  'member_count': 4,
  'camera_count': 2,
  'my_role': 'MEMBER_MANAGER',
  'my_nickname': 'Minh Anh',
};

List<Object?> groupsJson({String skyRole = 'MEMBER_MANAGER'}) => [
  personalGroupJson,
  {...skyGroupJson, 'my_role': skyRole},
];

const camerasJson = [
  {
    'cam_id': 'cam_charger',
    'cam_name': 'Hầm B1 · Khu sạc xe',
    'group_id': 'grp_sky_garden_01',
    'subgroup_id': 'sub_b1',
    'subgroup_name': 'Hầm B1',
    'device_name': 'Hikvision DS-2CD2143G2-I',
    'status': 'ONLINE',
    'last_seen_at': '2026-11-04T12:00:00Z',
    'live_stream_url': 'https://stream.matpho.vn/live/cam_charger/index.m3u8',
    'watch_area': {'left': 0.15, 'top': 0.20, 'width': 0.70, 'height': 0.65},
  },
  {
    'cam_id': 'cam_down',
    'cam_name': 'Lối xuống',
    'group_id': 'grp_sky_garden_01',
    'subgroup_id': 'sub_b2',
    'subgroup_name': 'Hầm B2',
    'device_name': null,
    'status': 'OFFLINE',
    'last_seen_at': '2026-11-04T14:30:00+00:00',
    'live_stream_url': null,
    'watch_area': null,
  },
];
