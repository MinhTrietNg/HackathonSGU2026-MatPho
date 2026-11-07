import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mat_pho/core/router/app_router.dart';
import 'package:mat_pho/core/theme/theme.dart';
import 'package:mat_pho/core/time_format.dart';
import 'package:mat_pho/core/widgets/mp_toast.dart';
import '../../fakes/fake_overrides.dart';
import '../../fakes/fake_data.dart';
import 'package:mat_pho/data/providers.dart';
import 'package:mat_pho/data/remote/camera_remote.dart';
import 'package:mat_pho/data/remote/group_remote.dart';
import 'package:mat_pho/features/auth/auth_session.dart';
import 'package:mat_pho/features/cameras/camera_monitor_screen.dart';
import 'package:mat_pho/features/cameras/camera_routes.dart';
import 'package:mat_pho/features/groups/group_state.dart'
    show groupCamerasProvider;

import '../../data/remote/group_camera_server.dart';

const _gid = 'grp_sky_garden_01';
const _rtsp =
    'rtsp://admin:MatKhau123@192.168.1.100:554/Streaming/Channels/101';
const _snapshot = 'http://api.matpho.vn/snapshots/temp_probe_99a.jpg';

class _SignedIn extends AuthSessionNotifier {
  @override
  AuthSession build() => const SignedIn(FakeData.user);
}

GroupCameraServer _sky({String role = 'MEMBER_MANAGER'}) => GroupCameraServer()
  ..on('GET', '/groups', groupsJson(skyRole: role))
  ..on('GET', '/cameras', camerasJson)
  ..on('GET', '/groups/$_gid/subgroups', [
    {'subgroup_id': 'sub_b1', 'name': 'Hầm B1', 'camera_count': 1},
    {'subgroup_id': 'sub_b2', 'name': 'Hầm B2', 'camera_count': 1},
  ])
  ..on('GET', '/groups/$_gid/members', {
    'members': [
      {
        'user_id': 'usr_lan',
        'full_name': 'Trần Thị Lan',
        'phone_number': '+84903112233',
        'role': 'LEADER',
        'nickname': 'Chị Lan',
        'camera_ids': null,
        'is_you': false,
      },
      {
        'user_id': 'usr_tuan',
        'full_name': 'Trần Anh Tuấn',
        'phone_number': '+84912000678',
        'role': 'MEMBER',
        'nickname': 'Chú Tuấn',
        'camera_ids': ['cam_charger'],
        'is_you': false,
      },
      {
        'user_id': 'usr_me',
        'full_name': 'Nguyễn Minh Anh',
        'phone_number': '+84912345678',
        'role': role,
        'nickname': 'Minh Anh',
        'camera_ids': null,
        'is_you': true,
      },
    ],
    'pending_invitations': [],
  });

Future<GoRouter> _pump(
  WidgetTester tester,
  GroupCameraServer server, {
  String initial = AppRoutes.monitor,
}) async {
  tester.view
    ..physicalSize = const Size(360, 780) * 2
    ..devicePixelRatio = 2;
  addTearDown(tester.view.reset);
  addTearDown(hideMpToast);
  final router = GoRouter(
    navigatorKey: rootNavigatorKey,
    initialLocation: initial,
    routes: [
      GoRoute(
        path: AppRoutes.monitor,
        builder: (_, _) => const CameraMonitorScreen(),
        routes: [
          ...cameraSubRoutes,
          GoRoute(
            path: 'watch/:id',
            builder: (_, state) => Text('watch ${state.pathParameters['id']}'),
          ),
        ],
      ),
    ],
  );
  addTearDown(router.dispose);
  await tester.pumpWidget(
    ProviderScope(
      overrides: fakeOverrides([
        authSessionProvider.overrideWith(_SignedIn.new),
        groupRepositoryProvider.overrideWith(
          (ref) => RemoteGroupRepository(server.api),
        ),
        cameraRepositoryProvider.overrideWith(
          (ref) => RemoteCameraRepository(server.api),
        ),
      ]),
      child: MaterialApp.router(
        theme: AppTheme.dark(),
        locale: const Locale('vi'),
        supportedLocales: const [Locale('vi')],
        localizationsDelegates: GlobalMaterialLocalizations.delegates,
        routerConfig: router,
      ),
    ),
  );
  await tester.pumpAndSettle();
  return router;
}

Future<void> _tap(WidgetTester tester, Finder finder) async {
  await tester.ensureVisible(finder);
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

Future<void> _connect(WidgetTester tester) async {
  expect(find.text('Thêm camera RTSP'), findsOneWidget);
  await tester.enterText(find.byType(TextField), _rtsp);
  await _tap(tester, find.text('Kết nối'));
}

void main() {
  testWidgets('I7 · a member sees only the cameras with a stream', (
    tester,
  ) async {
    await _pump(tester, _sky(role: 'MEMBER'));
    expect(find.text('Hầm B1 · Khu sạc xe'), findsOneWidget);
    expect(find.text('Lối xuống'), findsNothing);
  });

  testWidgets('I7 · a manager sees the lost camera too', (tester) async {
    await _pump(tester, _sky());
    expect(find.text('Hầm B1 · Khu sạc xe'), findsOneWidget);
    expect(find.text('Lối xuống'), findsOneWidget);
    final since = DateTime.utc(2026, 11, 4, 14, 30).toLocal();
    expect(
      find.text('Mất tín hiệu từ ${formatClock(since, seconds: false)}'),
      findsOneWidget,
    );
  });

  testWidgets('I7 · "Chỉ báo cháy" sees every camera, none with a stream', (
    tester,
  ) async {
    final server = _sky(role: 'NOTIFIER')
      ..on('GET', '/cameras', [
        for (final c in camerasJson) {...c, 'live_stream_url': null},
      ]);
    await _pump(tester, server);
    expect(find.text('Hầm B1 · Khu sạc xe'), findsOneWidget);
    expect(find.text('Lối xuống'), findsOneWidget);
  });

  group('groupCamerasProvider · the member rule (#75)', () {
    Future<List<String>> visible(String role) async {
      final server = _sky(role: role);
      final container = ProviderContainer(
        overrides: fakeOverrides([
          authSessionProvider.overrideWith(_SignedIn.new),
          groupRepositoryProvider.overrideWith(
            (ref) => RemoteGroupRepository(server.api),
          ),
          cameraRepositoryProvider.overrideWith(
            (ref) => RemoteCameraRepository(server.api),
          ),
        ]),
      );
      addTearDown(container.dispose);
      final cameras = await container.read(groupCamerasProvider(_gid).future);
      expect(server.calls.where((c) => c == 'GET /cameras'), hasLength(1));
      return [for (final c in cameras) c.id];
    }

    test('a member: cameras without a stream are hidden', () async {
      expect(await visible('MEMBER'), ['cam_charger']);
    });

    test('owner, manager and "Chỉ báo cháy" see them all', () async {
      for (final role in ['LEADER', 'MEMBER_MANAGER', 'NOTIFIER']) {
        expect(await visible(role), ['cam_charger', 'cam_down'], reason: role);
      }
    });
  });

  for (final code in const [
    'CAMERA_NO_RESPONSE',
    'CAMERA_AUTH_FAILED',
    'CAMERA_NOT_REACHABLE',
    'CAMERA_VENDOR_BLOCKED',
  ]) {
    testWidgets('$code opens I4 titled with the device name', (tester) async {
      final server = _sky()
        ..fail('POST', '/cameras/probe', 400, code, {
          'device_name': 'Hikvision',
          'host': '192.168.1.100',
        });
      await _pump(tester, server, initial: CameraRoutes.add);
      await _connect(tester);
      expect(server.body('POST', '/cameras/probe'), {'rtsp_url': _rtsp});
      expect(find.text('Hikvision'), findsOneWidget);
      expect(find.text('Không kết nối được'), findsOneWidget);
    });
  }

  testWidgets('I2 · server down: a toast, still on I2', (tester) async {
    final server = _sky()
      ..fail('POST', '/cameras/probe', 503, 'SERVICE_UNAVAILABLE');
    await _pump(tester, server, initial: CameraRoutes.add);
    await _connect(tester);
    expect(find.text('Thêm camera RTSP'), findsOneWidget);
    expect(find.text('Không kết nối được'), findsNothing);
    expect(find.byType(MpToast), findsOneWidget);
    await tester.pump(const Duration(seconds: 5));
    await tester.pumpAndSettle();
  });

  testWidgets('I5 · the probe picture; "Lưu" sends it all, whole picture', (
    tester,
  ) async {
    final server = _sky()
      ..on('POST', '/cameras/probe', {
        'device_name': 'Hikvision DS-2CD2143G2-I',
        'resolution': '1920x1080',
        'fps': 25,
        'preview_snapshot_url': _snapshot,
      })
      ..on('POST', '/cameras', {
        ...camerasJson.first,
        'cam_id': 'cam_new',
        'cam_name': 'Khu sạc xe',
      }, status: 201);
    final router = await _pump(tester, server, initial: CameraRoutes.add);
    await _connect(tester);
    expect(find.text('Đặt tên camera'), findsOneWidget);
    final picture = tester.widget<Image>(find.byType(Image));
    expect((picture.image as NetworkImage).url, _snapshot);

    await tester.enterText(find.byType(TextField), 'Khu sạc xe');
    await tester.pumpAndSettle();
    await _tap(tester, find.text('Lưu'));
    final body = server.body('POST', '/cameras')! as Map<String, Object?>;
    expect(body['group_id'], _gid);
    expect(body['subgroup_id'], 'sub_b1');
    expect(body['cam_name'], 'Khu sạc xe');
    expect(body['device_name'], 'Hikvision DS-2CD2143G2-I');
    expect(body['rtsp_url'], _rtsp);
    expect(body['watch_area'], {
      'left': 0.0,
      'top': 0.0,
      'width': 1.0,
      'height': 1.0,
    });
    expect(
      router.routerDelegate.currentConfiguration.last.matchedLocation,
      AppRoutes.watch('cam_new'),
    );
  });

  testWidgets('I5 · PERMISSION_DENIED on "Lưu": the J13 rule, still on I5', (
    tester,
  ) async {
    final server = _sky()
      ..on('POST', '/cameras/probe', {'device_name': 'Hikvision'})
      ..fail('POST', '/cameras', 403, 'PERMISSION_DENIED');
    await _pump(tester, server, initial: CameraRoutes.add);
    await _connect(tester);
    await tester.enterText(find.byType(TextField), 'Khu sạc xe');
    await tester.pumpAndSettle();
    await _tap(tester, find.text('Lưu'));
    expect(
      find.text('Chỉ chủ nhóm và quản lý mới mời người hoặc thêm camera.'),
      findsOneWidget,
    );
    expect(find.text('Đặt tên camera'), findsOneWidget);
    await tester.pump(const Duration(seconds: 5));
    await tester.pumpAndSettle();
  });

  testWidgets('I8 · GET /cameras/{id}; "Đã báo" names the owner and '
      'managers from the members, not notified_names', (tester) async {
    final server = _sky()
      ..on('GET', '/cameras/cam_down', {
        ...camerasJson.last,
        'notified_names': ['Trần Thị Lan', 'Trần Anh Tuấn'],
      });
    await _pump(tester, server, initial: CameraRoutes.signalLost('cam_down'));
    expect(server.calls, contains('GET /cameras/cam_down'));
    expect(find.text('Hầm B2 · Lối xuống'), findsOneWidget);
    expect(
      find.text('Khu này đang không được canh cháy. Đã báo Chị Lan.'),
      findsOneWidget,
    );
  });

  testWidgets('I8 · reconnect, then the camera read again opens E2', (
    tester,
  ) async {
    final server = _sky()
      ..on('GET', '/cameras/cam_down', camerasJson.last)
      ..on('POST', '/cameras/cam_down/reconnect', {
        'cam_id': 'cam_down',
        'cam_name': 'Lối xuống',
        'status': 'ONLINE',
        'live_stream_url': null,
      });
    final router = await _pump(
      tester,
      server,
      initial: CameraRoutes.signalLost('cam_down'),
    );
    server.on('GET', '/cameras/cam_down', {
      ...camerasJson.last,
      'status': 'ONLINE',
    });
    await _tap(tester, find.text('Thử kết nối lại'));
    expect(server.calls, contains('POST /cameras/cam_down/reconnect'));
    expect(
      router.routerDelegate.currentConfiguration.last.matchedLocation,
      AppRoutes.watch('cam_down'),
    );
  });
}
