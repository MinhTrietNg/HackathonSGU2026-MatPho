import 'package:flutter/material.dart';

import 'package:mat_pho/core/widgets/mp_tab_bar.dart';
import '../../fakes/fake_data.dart';
import 'package:mat_pho/data/models/models.dart';
import 'package:mat_pho/data/providers.dart';
import 'package:mat_pho/features/cameras/camera_state.dart';
import 'package:mat_pho/features/detection/detection_controller.dart';
import 'package:mat_pho/features/detection/watch_full_screen.dart';
import 'package:mat_pho/features/detection/watch_screen.dart';
import '../gallery_registry.dart';
import '../gallery_scope.dart';

typedef WatchDemo = ({
  String code,
  String title,
  DetectionState state,
  DateTime time,
  bool fullScreen,
});

DateTime _at(int h, int m, int s) => DateTime(2025, 10, 23, h, m, s);

final _fireCamera = CameraDetail(
  camera: FakeData.cameras.firstWhere((c) => c.id == FakeData.fireCameraId),
  group: FakeData.skyGarden,
  areaName: 'Hầm B1',
  notifiedNames: const [],
);

final _suspect = SuspectFrame(
  sign: FakeData.suspectSign,
  confidence: FakeData.suspectConfidence,
  detectedAt: _at(21, 47, 31),
);

const _detected = TimelineStep(TimelineStepKind.detected, Duration.zero);
const _imageSent = TimelineStep(
  TimelineStepKind.imageSent,
  FakeData.imageSentAfter,
);

final watchDemos = <WatchDemo>[
  (
    code: 'E2',
    title: 'Đang theo dõi',
    state: const DetectionWatching(),
    time: _at(21, 47, 12),
    fullScreen: false,
  ),
  (
    code: 'E2a',
    title: 'Thấy khói mờ',
    state: DetectionVerifying(suspect: _suspect, steps: const [_detected]),
    time: _at(21, 47, 12),
    fullScreen: false,
  ),
  (
    code: 'E2b',
    title: 'Khói dày dần',
    state: DetectionVerifying(
      suspect: _suspect,
      steps: const [_detected, _imageSent],
    ),
    time: _at(21, 47, 12),
    fullScreen: false,
  ),
  (
    code: 'E2c',
    title: 'Thấy lửa',
    state: DetectionVerifying(
      suspect: _suspect,
      steps: const [
        _detected,
        _imageSent,
        TimelineStep(
          TimelineStepKind.confirmedFire,
          FakeData.fireConfirmedAfter,
        ),
      ],
      verdict: SuspectFrame(
        sign: DetectedSign.fire,
        confidence: FakeData.fireConfidence,
        detectedAt: _at(21, 47, 31),
      ),
    ),
    time: _at(21, 47, 12),
    fullScreen: false,
  ),
  (
    code: 'E2d',
    title: 'Đang báo động',
    state: DetectionNotified(FakeData.fireAlert()),
    time: _at(21, 47, 12),
    fullScreen: false,
  ),
  (
    code: 'E4',
    title: 'Đã bác bỏ (toast)',
    state: DetectionDismissed(
      reason: FakeData.dismissalReason,
      event: FakeData.dismissedEvent(),
    ),
    time: _at(21, 47, 39),
    fullScreen: false,
  ),
  (
    code: 'E5',
    title: 'Mất kết nối',
    state: const DetectionOffline(),
    time: _at(21, 52, 3),
    fullScreen: false,
  ),
  (
    code: 'E6',
    title: 'Máy chậm / nóng',
    state: const DetectionDegraded(fromFps: normalFps, fps: degradedFps),
    time: _at(22, 10, 44),
    fullScreen: false,
  ),
  (
    code: 'E8',
    title: 'Toàn màn hình',
    state: const DetectionWatching(),
    time: _at(21, 47, 12),
    fullScreen: true,
  ),
];

final rowEEntries = <GalleryEntry>[
  for (final demo in watchDemos)
    GalleryEntry(
      code: demo.code,
      title: demo.title,
      builder: (_) => WatchPreview(demo),
    ),
];

class WatchPreview extends StatelessWidget {
  const WatchPreview(this.demo, {super.key});

  final WatchDemo demo;

  @override
  Widget build(BuildContext context) {
    final id = _fireCamera.camera.id;
    return GalleryScope(
      overrides: [
        cameraDetailProvider.overrideWith((ref, id) => _fireCamera),
        detectionControllerProvider.overrideWith2(
          (cameraId) => _ForcedDetection(cameraId, demo.state),
        ),
        clockProvider.overrideWithValue(() => demo.time),
      ],
      child: MediaQuery(
        data: MediaQuery.of(context).copyWith(disableAnimations: true),
        child: demo.fullScreen
            ? WatchFullScreen(cameraId: id)
            : Scaffold(
                body: WatchScreen(cameraId: id),
                bottomNavigationBar: MpTabBar(currentIndex: 0, onTap: (_) {}),
              ),
      ),
    );
  }
}

class _ForcedDetection extends DetectionController {
  _ForcedDetection(super.cameraId, this._state);

  final DetectionState _state;

  @override
  DetectionState build() => _state;

  @override
  void start(Camera camera) {}

  @override
  void dismissSuspect() {}
}
