import 'package:flutter/material.dart';
import 'package:flutter_riverpod/misc.dart' show Override;

import 'package:mat_pho/core/widgets/mp_tab_bar.dart';
import 'package:mat_pho/core/widgets/mp_toast.dart';
import 'package:mat_pho/data/errors.dart';
import '../../fakes/fake_data.dart';
import '../../fakes/fake_overrides.dart';
import '../../fakes/fake_world.dart';
import 'package:mat_pho/data/models/models.dart';
import 'package:mat_pho/features/cameras/add_camera_screen.dart';
import 'package:mat_pho/features/cameras/camera_actions_sheet.dart';
import 'package:mat_pho/features/cameras/camera_monitor_screen.dart';
import 'package:mat_pho/features/cameras/camera_screen.dart';
import 'package:mat_pho/features/cameras/camera_state.dart';
import 'package:mat_pho/features/cameras/connect_error_screen.dart';
import 'package:mat_pho/features/cameras/name_camera_screen.dart';
import 'package:mat_pho/features/cameras/new_area_sheet.dart';
import 'package:mat_pho/features/cameras/monitor_toasts.dart';
import 'package:mat_pho/features/cameras/place_picker_sheet.dart';
import 'package:mat_pho/features/groups/current_group.dart';
import 'package:mat_pho/features/settings/camera_trash_screen.dart';
import '../gallery_registry.dart';
import '../gallery_scope.dart';

const _hamXe = 'Hầm xe';

Override _place(String groupId) =>
    currentGroupIdProvider.overrideWith(() => _PresetPlace(groupId));

const _probe = CameraProbe(
  rtspUrl: FakeData.rtspExample,
  deviceName: FakeData.probedDeviceName,
);

final _namedFlow = addCameraProvider.overrideWith(
  () => _PresetFlow(
    const AddCameraState(
      rtspUrl: FakeData.rtspExample,
      probe: _probe,
      name: 'Khu sạc xe',
    ),
  ),
);

final rowIEntries = <GalleryEntry>[
  GalleryEntry(
    code: 'I2',
    title: 'Kết nối camera RTSP',
    builder: (_) =>
        const GalleryScope(child: AddCameraScreen(previewFocused: true)),
  ),
  GalleryEntry(
    code: 'I4',
    title: 'Không kết nối được',
    builder: (_) => GalleryScope(
      overrides: [
        addCameraProvider.overrideWith(
          () => _PresetFlow(
            const AddCameraState(
              rtspUrl: FakeData.rtspExample,
              error: CameraNoResponseException(
                cameraName: FakeData.probedDeviceName,
              ),
            ),
          ),
        ),
      ],
      child: const ConnectErrorScreen(),
    ),
  ),
  GalleryEntry(
    code: 'I5',
    title: 'Đặt tên & vùng theo dõi',
    builder: (_) =>
        GalleryScope(overrides: [_namedFlow], child: const NameCameraScreen()),
  ),
  GalleryEntry(
    code: 'I7',
    title: 'Theo dõi · camera RTSP',
    builder: (_) => GalleryScope(child: const _TabFrame(CameraMonitorScreen())),
  ),
  GalleryEntry(
    code: 'I8',
    title: 'Camera mất tín hiệu',
    builder: (_) => GalleryScope(
      overrides: [
        fakeWorldProvider.overrideWith((ref) {
          final world = FakeWorld(ref.watch(fakeScenarioProvider));
          ref.onDispose(world.dispose);
          world.members[FakeData.skyGarden.id] = [
            for (final m in world.members[FakeData.skyGarden.id]!)
              m.id == 'm-lan' ? m.copyWith(nickname: 'chị Lan') : m,
          ];
          return world;
        }),
      ],
      child: const CameraScreen(cameraId: 'cam-down'),
    ),
  ),
  GalleryEntry(
    code: 'I9',
    title: 'Khu vực mới (overlay)',
    builder: (_) => GalleryScope(
      overrides: [_namedFlow],
      child: _ShowOnStart(
        show: (context) => showNewAreaSheet(
          context,
          initialName: FakeData.newAreaExample,
          previewFocused: true,
        ),
        child: const NameCameraScreen(),
      ),
    ),
  ),
  GalleryEntry(
    code: 'I10',
    title: 'Theo dõi · vừa báo nhầm',
    builder: (_) => GalleryScope(
      child: _TabFrame(
        const CameraMonitorScreen(),
        onShown: (context) => showFalseAlarmToastFor(
          context,
          locationName: _hamXe,
          onUndo: () {},
          duration: null,
        ),
      ),
    ),
  ),
  GalleryEntry(
    code: 'I11',
    title: 'Theo dõi · Nhà mình',
    builder: (_) => GalleryScope(
      overrides: [_place(FakeData.home.id)],
      child: const _TabFrame(CameraMonitorScreen()),
    ),
  ),
  GalleryEntry(
    code: 'I12',
    title: 'Theo dõi · công ty (thành viên)',
    builder: (_) => GalleryScope(
      overrides: [_place(FakeData.office.id)],
      child: const _TabFrame(CameraMonitorScreen()),
    ),
  ),
  GalleryEntry(
    code: 'I13',
    title: 'Chọn nơi (overlay · Chung cư Sky Garden)',
    builder: (_) => GalleryScope(
      child: const _TabFrame(CameraMonitorScreen(), onShown: showPlacePicker),
    ),
  ),
  GalleryEntry(
    code: 'I14',
    title: 'Chọn nơi (overlay · Nhà mình)',
    builder: (_) => GalleryScope(
      overrides: [_place(FakeData.home.id)],
      child: const _TabFrame(CameraMonitorScreen(), onShown: showPlacePicker),
    ),
  ),
  GalleryEntry(
    code: 'I15',
    title: 'Chọn nơi (overlay · Văn phòng công ty)',
    builder: (_) => GalleryScope(
      overrides: [_place(FakeData.office.id)],
      child: const _TabFrame(CameraMonitorScreen(), onShown: showPlacePicker),
    ),
  ),
  GalleryEntry(
    code: 'I16',
    title: 'Theo dõi · vừa xử lý',
    builder: (_) => GalleryScope(
      child: _TabFrame(
        const CameraMonitorScreen(),
        onShown: (context) => showResolvedToastFor(
          context,
          locationName: _hamXe,
          onUndo: () {},
          duration: null,
        ),
      ),
    ),
  ),
  GalleryEntry(
    code: 'I8-NORTSP',
    title: 'Camera chưa có đường dẫn RTSP',
    builder: (_) => GalleryScope(
      overrides: [_downWithoutRtsp],
      child: const CameraScreen(cameraId: 'cam-down'),
    ),
  ),
  GalleryEntry(
    code: 'I20',
    title: 'Gỡ RTSP hay xoá camera (sheet)',
    builder: (_) => GalleryScope(
      child: _ShowOnStart(
        show: (context) => showCameraActionsSheet(
          context,
          FakeData.cameras.firstWhere((c) => c.id == 'cam-down'),
        ),
        child: const CameraScreen(cameraId: 'cam-down'),
      ),
    ),
  ),
  GalleryEntry(
    code: 'I18',
    title: 'Camera đã xoá (thùng rác 30 ngày)',
    builder: (_) => GalleryScope(
      overrides: [_trashedWorld],
      child: const CameraTrashScreen(),
    ),
  ),
];

// "Lối xuống" after "Gỡ đường dẫn RTSP".
final _downWithoutRtsp = fakeWorldProvider.overrideWith((ref) {
  final world = FakeWorld(ref.watch(fakeScenarioProvider));
  ref.onDispose(world.dispose);
  final down = world.cameras.firstWhere((c) => c.id == 'cam-down');
  world.cameras[world.cameras.indexOf(down)] = down.copyWith(hasRtsp: false);
  return world;
});

// Two Sky Garden cameras in the trash: one about to be purged, one fresh.
final _trashedWorld = fakeWorldProvider.overrideWith((ref) {
  final world = FakeWorld(ref.watch(fakeScenarioProvider));
  ref.onDispose(world.dispose);
  for (final (id, areaName, daysAgo) in [
    ('cam-charger', 'Hầm B1', 28),
    ('cam-ramp', 'Hầm B1', 7),
  ]) {
    final camera = world.cameras.firstWhere((c) => c.id == id);
    world.cameras.remove(camera);
    final deletedAt = world.now().subtract(Duration(days: daysAgo));
    world.trash.add((
      entry: TrashedCamera(
        id: camera.id,
        groupId: camera.groupId,
        name: camera.name,
        areaId: camera.areaId,
        areaName: areaName,
        deviceName: camera.deviceName,
        deletedAt: deletedAt,
        purgeAt: deletedAt.add(FakeWorld.trashRetention),
      ),
      camera: camera,
    ));
  }
  return world;
});

class _TabFrame extends StatelessWidget {
  const _TabFrame(this.child, {this.onShown});

  final Widget child;
  final void Function(BuildContext context)? onShown;

  @override
  Widget build(BuildContext context) {
    final screen = Scaffold(
      body: child,
      bottomNavigationBar: MpTabBar(currentIndex: 0, onTap: (_) {}),
    );
    return PopScope(
      onPopInvokedWithResult: (didPop, _) {
        if (didPop) hideMpToast();
      },
      child: onShown == null
          ? screen
          : _ShowOnStart(show: onShown!, child: screen),
    );
  }
}

class _ShowOnStart extends StatefulWidget {
  const _ShowOnStart({required this.show, required this.child});

  final void Function(BuildContext context) show;
  final Widget child;

  @override
  State<_ShowOnStart> createState() => _ShowOnStartState();
}

class _ShowOnStartState extends State<_ShowOnStart> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) widget.show(context);
    });
  }

  @override
  Widget build(BuildContext context) => widget.child;
}

class _PresetPlace extends CurrentGroup {
  _PresetPlace(this.groupId);

  final String groupId;

  @override
  String? build() => groupId;
}

class _PresetFlow extends AddCameraNotifier {
  _PresetFlow(this.preset);

  final AddCameraState preset;

  @override
  AddCameraState build() => preset;
}
