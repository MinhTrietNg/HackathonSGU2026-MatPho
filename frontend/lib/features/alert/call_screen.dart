library;

import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/router/app_router.dart';
import '../../core/theme/theme.dart';
import '../../core/time_format.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_fill_scroll_view.dart';
import 'alert_actions.dart';
import 'alert_controller.dart';
import 'alert_widgets.dart';

class CallScreen extends ConsumerStatefulWidget {
  const CallScreen({
    super.key,
    required this.eventId,
    this.connectedFor = Duration.zero,
  });

  final String eventId;

  final Duration connectedFor;

  @override
  ConsumerState<CallScreen> createState() => _CallScreenState();
}

class _CallScreenState extends ConsumerState<CallScreen> {
  late Duration _elapsed = widget.connectedFor;
  late final Timer _timer;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      setState(() => _elapsed += const Duration(seconds: 1));
    });
  }

  @override
  void dispose() {
    _timer.cancel();
    super.dispose();
  }

  void _end() {
    ref.read(alertProvider(widget.eventId).notifier).resolve();
    popOrGo(context, AppRoutes.alert(widget.eventId));
  }

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final event = ref.watch(alertProvider(widget.eventId)).value?.event;
    final natural = t.body.copyWith(height: kTextHeightNone);
    String two(int v) => v.toString().padLeft(2, '0');
    final clock = '${two(_elapsed.inMinutes)}:${two(_elapsed.inSeconds % 60)}';
    final script = event?.callScript;
    return Scaffold(
      body: Stack(
        children: [
          const AlertGlow(top: -122),
          SafeArea(
            child: MpFillScrollView(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 8, 20, 28),
                child: Column(
                  spacing: 20,
                  children: [
                    Padding(
                      padding: const EdgeInsets.only(top: 48),
                      child: Column(
                        spacing: 10,
                        children: [
                          const _Avatar(),
                          Text(
                            '114',
                            style: natural.copyWith(
                              fontSize: 64,
                              fontWeight: FontWeight.w800,
                              letterSpacing: -1.28,
                              color: c.textPrimary,
                            ),
                          ),
                          Text(
                            'Cứu hỏa · Cảnh sát PCCC',
                            style: natural.copyWith(
                              fontSize: 15,
                              fontWeight: FontWeight.w600,
                              color: c.textSecondary,
                            ),
                          ),
                          _ConnectedPill(label: 'Đã kết nối · $clock'),
                        ],
                      ),
                    ),
                    const Spacer(),
                    if (event != null)
                      _ReadOutCard(
                        address: event.address ?? event.locationName,
                        detail: script == null
                            ? null
                            : '$script · từ '
                                  '${formatClock(event.detectedAt, seconds: false)}',
                      ),
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 20),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          _Control(
                            label: 'Loa ngoài',
                            icon: MpIcons.sound,
                            onTap: () {},
                          ),
                          _Control(
                            label: 'Kết thúc',
                            icon: MpIcons.call,
                            hangUp: true,
                            onTap: _end,
                          ),
                          _Control(
                            label: 'Xem camera',
                            icon: MpIcons.camera,
                            onTap: () =>
                                openEventCamera(context, ref, widget.eventId),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _Avatar extends StatelessWidget {
  const _Avatar();

  @override
  Widget build(BuildContext context) {
    final fire = context.mpColors.statusFire;
    Widget disc(double size, double opacity) => Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: fire.withValues(alpha: opacity),
        shape: BoxShape.circle,
      ),
    );
    return SizedBox.square(
      dimension: 168,
      child: Stack(
        alignment: Alignment.center,
        children: [
          disc(168, 0.12),
          disc(136, 0.22),
          disc(104, 1),
          MpScaledIcon(
            MpIcons.call,
            color: context.mpColors.textPrimary,
            size: 44,
          ),
        ],
      ),
    );
  }
}

class _ConnectedPill extends StatelessWidget {
  const _ConnectedPill({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: c.statusOkSoft,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        spacing: 8,
        children: [
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(
              color: c.statusOk,
              shape: BoxShape.circle,
            ),
          ),
          Text(
            label,
            style: context.mpText.mono.copyWith(
              fontSize: 13,
              fontWeight: FontWeight.w600,
              height: kTextHeightNone,
              color: c.statusOk,
            ),
          ),
        ],
      ),
    );
  }
}

class _ReadOutCard extends StatelessWidget {
  const _ReadOutCard({required this.address, this.detail});

  final String address;
  final String? detail;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final natural = context.mpText.body.copyWith(height: kTextHeightNone);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration: BoxDecoration(
        color: c.bgCard,
        border: Border.all(color: c.lineSubtle),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        spacing: 6,
        children: [
          Text(
            'ĐỌC CHO TỔNG ĐÀI',
            style: natural.copyWith(
              fontSize: 11,
              fontWeight: FontWeight.w700,
              color: c.textMuted,
            ),
          ),
          Text(
            address,
            style: natural.copyWith(
              fontSize: 16,
              fontWeight: FontWeight.w700,
              color: c.textPrimary,
            ),
          ),
          if (detail case final detail?)
            Text(
              detail,
              style: natural.copyWith(
                fontSize: 13,
                fontWeight: FontWeight.w500,
                color: c.textSecondary,
              ),
            ),
        ],
      ),
    );
  }
}

class _Control extends StatelessWidget {
  const _Control({
    required this.label,
    required this.icon,
    required this.onTap,
    this.hangUp = false,
  });

  final String label;
  final String icon;
  final VoidCallback onTap;
  final bool hangUp;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final size = hangUp ? 72.0 : 64.0;
    return Semantics(
      button: true,
      label: label,
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          spacing: 8,
          children: [
            Container(
              width: size,
              height: size,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: hangUp ? c.statusFire : c.bgRaised,
                shape: BoxShape.circle,
              ),
              child: hangUp
                  ? Transform.rotate(
                      angle: -135 * math.pi / 180,
                      child: MpScaledIcon(
                        icon,
                        color: c.textPrimary,
                        size: 28.8,
                      ),
                    )
                  : MpScaledIcon(icon, color: c.textPrimary, size: 25.6),
            ),
            Text(
              label,
              style: context.mpText.caption.copyWith(
                fontWeight: FontWeight.w600,
                height: kTextHeightNone,
                color: c.textSecondary,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
