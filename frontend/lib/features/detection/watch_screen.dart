library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import '../../core/theme/theme.dart';
import '../../core/time_format.dart';
import '../../core/widgets/mp_banner.dart';
import '../../core/widgets/mp_button.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_header.dart';
import '../../core/widgets/mp_illustration.dart';
import '../../core/widgets/mp_tips_card.dart';
import '../../core/widgets/mp_toast.dart';
import '../../data/models/models.dart';
import '../../data/providers.dart';
import '../ai_mode/ai_mode_state.dart';
import '../alert/alert_actions.dart' show callEmergency;
import '../cameras/camera_state.dart';
import 'detection_controller.dart';
import 'detection_routes.dart';
import 'feed_player.dart';
import 'feed_snapshot.dart';
import 'watch_widgets.dart';

class WatchScreen extends ConsumerStatefulWidget {
  const WatchScreen({super.key, required this.cameraId});

  final String cameraId;

  @override
  ConsumerState<WatchScreen> createState() => _WatchScreenState();
}

class _WatchScreenState extends ConsumerState<WatchScreen> {
  bool _autoStarted = false;

  final _feed = FeedSnapshotTarget();

  @override
  void initState() {
    super.initState();
    ref.listenManual(detectionControllerProvider(widget.cameraId), _onState);
    ref.listenManual(watchCameraProvider(widget.cameraId), (_, next) {
      if (next case AsyncData(:final value)) _autoStart(value.camera);
    }, fireImmediately: true);
  }

  DetectionController get _controller =>
      ref.read(detectionControllerProvider(widget.cameraId).notifier);

  void _autoStart(Camera camera) {
    if (_autoStarted) return;
    _autoStarted = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted &&
          ref.read(detectionControllerProvider(widget.cameraId))
              is DetectionIdle) {
        _controller.start(camera);
      }
    });
  }

  void _onState(DetectionState? previous, DetectionState next) {
    final alert = switch (next) {
      DetectionNotified(openAlert: true, :final alert) ||
      DetectionUnverified(:final alert) => alert,
      _ => null,
    };
    if (alert == null) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final path = GoRouter.of(context).state.uri.path;
      final watch = AppRoutes.watch(widget.cameraId);
      if (path == watch || path.startsWith('$watch/')) {
        context.push(AppRoutes.alert(alert.id));
      }
    });
  }

  void _back() {
    if (context.canPop()) {
      context.pop();
    } else {
      _snapshot();
      context.go(AppRoutes.monitor);
    }
  }

  // Leaving with a live frame on screen: it becomes the camera's thumbnail.
  void _snapshot() {
    final boundary = _feed.boundary;
    final camera = ref.read(watchCameraProvider(widget.cameraId)).value?.camera;
    if (boundary == null || camera == null) return;
    final source = ref.read(cameraFeedProvider(camera));
    if (source == null ||
        !feedShowsFrame(ref.read(feedPlayerProvider(source)).value)) {
      return;
    }
    final thumbnails = ref.read(cameraThumbnailsProvider.notifier);
    unawaited(() async {
      try {
        final png = await snapshotFeed(boundary);
        if (png != null) thumbnails.capture(camera.id, png);
      } on Object {
        // No thumbnail this time; the old one stays.
      }
    }());
  }

  @override
  Widget build(BuildContext context) {
    final camera = ref.watch(watchCameraProvider(widget.cameraId));
    final state = ref.watch(detectionControllerProvider(widget.cameraId));
    return PopScope(
      onPopInvokedWithResult: (didPop, _) {
        if (didPop) _snapshot();
      },
      child: _scaffold(camera, state),
    );
  }

  Widget _scaffold(AsyncValue<CameraDetail> camera, DetectionState state) {
    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 14),
              child: MpHeader.back(
                title: camera.value?.title ?? '',
                onBack: _back,
              ),
            ),
            Expanded(
              child: switch (camera) {
                AsyncData(:final value) => _session(value, state),
                AsyncError() => const _CameraMissing(),
                _ => const SizedBox.shrink(),
              },
            ),
          ],
        ),
      ),
    );
  }

  Widget _session(CameraDetail camera, DetectionState state) {
    final noAnimation = MediaQuery.disableAnimationsOf(context);
    return AnimatedSwitcher(
      duration: noAnimation ? Duration.zero : const Duration(milliseconds: 200),
      switchInCurve: Curves.easeOut,
      switchOutCurve: Curves.easeOut,
      child: Padding(
        key: ValueKey(_layoutOf(state)),
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          spacing: 14,
          children: _body(camera, state),
        ),
      ),
    );
  }

  Object _layoutOf(DetectionState state) => switch (state) {
    DetectionDismissed() => 'E4',
    DetectionOffline() => 'E5',
    DetectionDegraded() => 'E6',
    _ => 'E2',
  };

  List<Widget> _body(CameraDetail camera, DetectionState state) {
    final c = context.mpColors;
    final clock = ref.watch(clockProvider);
    final place = camera.areaName ?? camera.camera.name;
    final video = ref.watch(cameraFeedProvider(camera.camera));
    WatchFeed feed({Color Function(MpColors c)? border}) => WatchFeed(
      art: watchArtOf(state),
      place: place,
      clock: clock,
      border: border,
      video: video,
      still: ref.watch(cameraStillProvider(camera.camera)),
      snapshot: _feed,
      onFullScreen: () =>
          context.push(DetectionPaths.fullScreen(widget.cameraId)),
    );

    switch (state) {
      case DetectionIdle() || DetectionWatching() || DetectionUnverified():
        return [
          feed(),
          WatchTicker(
            clock: clock,
            builder: (now) => WatchStatusCard(
              rows: [
                switch (aiActivityAt(camera.camera.ai, now)) {
                  AiActivity.scanning => _scanning(_fpsOf(state)),
                  final idle => _aiIdle(idle),
                },
              ],
            ),
          ),
        ];

      case DetectionVerifying(
        :final steps,
        :final verdict,
        :final fps,
        :final awaitingVerdict,
      ):
        return [
          feed(border: verdict == null ? null : (c) => c.statusFire),
          WatchStatusCard(
            rows: [
              _scanning(fps),
              ..._steps(steps, fireConfidence: verdict?.confidence),
            ],
            link: awaitingVerdict ? 'Không phải cháy? Bỏ qua' : null,
            onLink: _controller.dismissSuspect,
          ),
        ];

      case DetectionNotified(:final alert, :final fps):
        final latency = alert.notifyLatency;
        return [
          feed(border: (c) => c.statusFire),
          WatchStatusCard(
            rows: [
              _scanning(fps),
              ..._steps(alert.timeline, fireConfidence: alert.confidence),
            ],
            summary: latency == null
                ? null
                : 'Báo sau ${formatStepSeconds(latency)} giây',
          ),
        ];

      case DetectionDismissed(:final reason, :final event, :final fps):
        return [
          feed(),
          WatchStatusCard(rows: [_scanning(fps)]),
          const WatchNote(
            icon: MpIcons.shield,
            text: 'Hình ảnh chỉ nằm trên máy này.',
          ),
          const Spacer(),
          MpToast.rich(
            thumbnail: const MpIllustration(
              MpIllustrations.dismissed,
              size: MpToast.thumbnailArtSize,
            ),
            title: 'Không phải cháy',
            subtitle: reason.explanation,
            actionLabel: 'Xem',
            onAction: () => context.push(AppRoutes.historyDetail(event.id)),
          ),
        ];

      case DetectionOffline(:final fps):
        return [
          const MpBanner(
            tone: MpBannerTone.warn,
            thumbnail: MpIllustration(
              MpIllustrations.offline,
              size: MpBanner.thumbnailArtSize,
            ),
            title: 'Mất mạng',
            body: 'Mất kết nối. Có mạng sẽ tự nối lại.',
          ),
          feed(),
          WatchStatusCard(
            rows: [
              _scanning(
                fps,
                description: 'Mất kết nối · Có mạng sẽ tự nối lại',
              ),
            ],
          ),
          const Spacer(),
          MpButton(
            label: 'Gọi 114 nếu thấy khói thật',
            icon: MpIcons.call,
            kind: MpButtonKind.secondary,
            onPressed: () => callEmergency(context, ref),
          ),
        ];

      case DetectionDegraded(:final fps):
        return [
          const MpBanner(
            tone: MpBannerTone.accent,
            thumbnail: MpIllustration(
              MpIllustrations.slowDevice,
              size: MpBanner.thumbnailArtSize,
            ),
            title: 'Máy nóng, đã quét chậm lại',
            body: 'Vẫn phát hiện được cháy, chậm hơn khoảng 1 giây.',
          ),
          feed(),
          WatchStatusCard(rows: [_scanning(fps, valueColor: c.statusWarn)]),
          const MpTipsCard(
            tips: [
              (MpIcons.battery, 'Cắm sạc'),
              (MpIcons.close, 'Tắt các app khác'),
            ],
          ),
        ];
    }
  }

  int _fpsOf(DetectionState state) => switch (state) {
    DetectionWatching(:final fps) || DetectionUnverified(:final fps) => fps,
    _ => normalFps,
  };

  WatchStatusRow _scanning(int fps, {String? description, Color? valueColor}) =>
      (
        dot: context.mpColors.statusOk,
        title: 'AI đang quét',
        value: '$fps khung/giây',
        valueColor: valueColor,
        description: description,
        bold: false,
      );

  WatchStatusRow _aiIdle(AiActivity activity) => (
    dot: activity == AiActivity.off
        ? context.mpColors.statusWarn
        : context.mpColors.brandAccentFg,
    title: aiActivityLabel(activity),
    value: null,
    valueColor: null,
    description: null,
    bold: false,
  );

  List<WatchStatusRow> _steps(
    List<TimelineStep> steps, {
    double? fireConfidence,
  }) {
    final c = context.mpColors;
    final shown = [
      for (final step in steps)
        if (step.offset != null &&
            const {
              TimelineStepKind.detected,
              TimelineStepKind.imageSent,
              TimelineStepKind.confirmedFire,
              TimelineStepKind.notified,
            }.contains(step.kind))
          step,
    ];
    final percent = ((fireConfidence ?? 0) * 100).round();
    return [
      for (final (i, step) in shown.indexed)
        (
          dot: switch (step.kind) {
            TimelineStepKind.detected => c.statusWarn,
            TimelineStepKind.notified => c.statusFire,
            _ => c.brandAccent,
          },
          title: switch (step.kind) {
            TimelineStepKind.detected => 'Máy phát hiện khói',
            TimelineStepKind.imageSent => 'Gửi ảnh',
            TimelineStepKind.confirmedFire => 'Xác nhận cháy',
            _ => 'Báo tới điện thoại',
          },
          value: formatOffset(step.offset!),
          valueColor: null,
          description: switch (step.kind) {
            TimelineStepKind.detected =>
              'Vùng mờ xám bốc lên qua 3 khung liên tiếp.',
            TimelineStepKind.imageSent => 'Gửi khung hình cho AI soi kỹ hơn.',
            TimelineStepKind.confirmedFire =>
              'Thấy lửa cam dưới xe máy, độ tin cậy $percent%.',
            _ => 'Đã báo cho bạn và đội trực ca.',
          },
          bold: i == shown.length - 1,
        ),
    ];
  }
}

class _CameraMissing extends StatelessWidget {
  const _CameraMissing();

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    return Center(
      child: Text(
        'Không tìm thấy camera.',
        style: context.mpText.body.copyWith(color: c.textSecondary),
      ),
    );
  }
}
