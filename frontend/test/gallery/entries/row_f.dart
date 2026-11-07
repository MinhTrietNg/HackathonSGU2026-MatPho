import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:mat_pho/core/widgets/mp_banner.dart';
import 'package:mat_pho/core/widgets/mp_sheet.dart';
import 'package:mat_pho/core/widgets/mp_tab_bar.dart';
import '../../fakes/fake_data.dart';
import '../../fakes/fake_overrides.dart';
import '../../fakes/fake_world.dart';
import 'package:mat_pho/data/models/fire_event.dart';
import 'package:mat_pho/features/alert/alert_controller.dart';
import 'package:mat_pho/features/alert/alert_dialogs.dart';
import 'package:mat_pho/features/alert/alert_listener.dart';
import 'package:mat_pho/features/alert/alert_screen.dart';
import 'package:mat_pho/features/alert/alert_sheets.dart';
import 'package:mat_pho/features/alert/call_screen.dart';
import 'package:mat_pho/features/alert/dialer_screen.dart';
import 'package:mat_pho/features/alert/lock_screen_mock.dart';
import 'package:mat_pho/features/auth/auth_session.dart';
import 'package:mat_pho/features/history/history_screen.dart';
import '../gallery_registry.dart';
import '../gallery_scope.dart';

final _fire = FakeData.fireAlert(id: 'evt-live');

final _unverified = FakeData.unverifiedEvent(
  id: 'evt-live-unverified',
  detectedAt: DateTime(2025, 10, 23, 21, 52, 10),
);

final rowFEntries = <GalleryEntry>[
  GalleryEntry(
    code: 'F1',
    title: 'Thông báo màn hình khoá (mock)',
    builder: (_) => LockScreenMock(event: _fire, now: FakeData.demoNow),
  ),
  GalleryEntry(
    code: 'F2',
    title: 'Cảnh báo cháy',
    builder: (_) => _AlertDemo(
      events: [_fire],
      builder: (_) => AlertScreen(eventId: _fire.id),
    ),
  ),
  GalleryEntry(
    code: 'F7',
    title: 'Đang gọi 114',
    builder: (_) => _AlertDemo(
      events: [_fire],
      builder: (_) => CallScreen(
        eventId: _fire.id,
        connectedFor: const Duration(seconds: 12),
      ),
    ),
  ),
  GalleryEntry(
    code: 'F5',
    title: 'Đã xử lý',
    builder: (_) => _AlertDemo(
      events: [_fire],
      builder: (_) => AlertScreen(eventId: _fire.id),
      onReady: (_, container) async {
        final alert = alertProvider(_fire.id);
        final allowed = Completer<void>();
        final sub = container.listen(alert, (_, next) {
          if (next.value?.closing == AlertClosing.allowed &&
              !allowed.isCompleted) {
            allowed.complete();
          }
        }, fireImmediately: true);
        await allowed.future;
        sub.close();
        container.read(alert.notifier).resolve();
      },
    ),
  ),
  GalleryEntry(
    code: 'F4',
    title: 'Nghi ngờ · chưa xác minh được',
    builder: (_) => _AlertDemo(
      events: [_unverified],
      builder: (_) => AlertScreen(eventId: _unverified.id),
    ),
  ),
  GalleryEntry(
    code: 'F6',
    title: 'Banner khi đang ở tab khác',
    builder: (_) => _AlertDemo(
      events: const [],
      builder: (_) => const Scaffold(
        body: AlertListener(child: HistoryScreen()),
        bottomNavigationBar: MpTabBar(currentIndex: 1, onTap: _noop),
      ),
      onReady: (_, container) =>
          container.read(fakeWorldProvider).addEvent(_fire, alert: true),
      onLeave: hideMpAlertBanner,
    ),
  ),
  GalleryEntry(
    code: 'F8',
    title: 'Trình gọi điện · 114',
    builder: (_) => _AlertDemo(
      events: [_fire],
      builder: (_) => DialerScreen(eventId: _fire.id),
    ),
  ),
  GalleryEntry(
    code: 'F9',
    title: 'Xác nhận báo nhầm (overlay)',
    builder: (_) => _OverlayDemo(show: (context) => confirmFalseAlarm(context)),
  ),
  GalleryEntry(
    code: 'F10',
    title: 'Xác nhận đã xử lý (overlay)',
    builder: (_) => _OverlayDemo(show: (context) => confirmResolved(context)),
  ),
  GalleryEntry(
    code: 'F-SHEET-END',
    title: 'mp/Sheet · Kết thúc sự cố (không còn trong luồng)',
    builder: (_) => _OverlayDemo(
      show: (context) =>
          showMpSheet<int>(context, builder: (_) => const EndIncidentSheet()),
    ),
  ),
  GalleryEntry(
    code: 'F-SHEET-FALSE',
    title: 'mp/Sheet · Báo nhầm (không còn trong luồng)',
    builder: (_) => _OverlayDemo(
      show: (context) => showMpSheet<String>(
        context,
        builder: (_) => const FalseAlarmReasonSheet(),
      ),
    ),
  ),
];

void _noop(int _) {}

class _AlertDemo extends StatefulWidget {
  const _AlertDemo({
    required this.events,
    required this.builder,
    this.onReady,
    this.onLeave,
  });

  final List<FireEvent> events;
  final WidgetBuilder builder;
  final void Function(BuildContext context, ProviderContainer container)?
  onReady;
  final VoidCallback? onLeave;

  @override
  State<_AlertDemo> createState() => _AlertDemoState();
}

class _AlertDemoState extends State<_AlertDemo> {
  final _innerKey = GlobalKey();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final inner = _innerKey.currentContext;
      if (inner == null) return;
      widget.onReady?.call(inner, ProviderScope.containerOf(inner));
    });
  }

  @override
  void dispose() {
    widget.onLeave?.call();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return GalleryScope(
      overrides: [
        authSessionProvider.overrideWith(_SignedIn.new),
        fakeWorldProvider.overrideWith((ref) {
          final world = FakeWorld(ref.watch(fakeScenarioProvider));
          for (final event in widget.events.reversed) {
            world.addEvent(event);
          }
          ref.onDispose(world.dispose);
          return world;
        }),
      ],
      child: Builder(key: _innerKey, builder: widget.builder),
    );
  }
}

class _OverlayDemo extends StatefulWidget {
  const _OverlayDemo({required this.show});

  final void Function(BuildContext context) show;

  @override
  State<_OverlayDemo> createState() => _OverlayDemoState();
}

class _OverlayDemoState extends State<_OverlayDemo> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) widget.show(context);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () => widget.show(context),
      ),
    );
  }
}

class _SignedIn extends AuthSessionNotifier {
  @override
  AuthSession build() => const SignedIn(FakeData.user);
}
