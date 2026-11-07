library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import '../../core/theme/theme.dart';
import '../../core/widgets/mp_area_picker.dart';
import '../../core/widgets/mp_button.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_header.dart';
import '../../core/widgets/mp_illustration.dart';
import '../../core/widgets/mp_page.dart';
import '../../core/widgets/mp_text_field.dart';
import '../../data/errors.dart';
import '../../data/models/models.dart';
import '../../data/providers.dart';
import '../groups/group_widgets.dart' show showGroupFailureToast;
import 'camera_state.dart';
import 'camera_widgets.dart';
import 'new_area_sheet.dart';

class NameCameraScreen extends ConsumerStatefulWidget {
  const NameCameraScreen({super.key});

  @override
  ConsumerState<NameCameraScreen> createState() => _NameCameraScreenState();
}

class _NameCameraScreenState extends ConsumerState<NameCameraScreen> {
  late final _name = TextEditingController(
    text: ref.read(addCameraProvider).name,
  );

  AddCameraNotifier get _flow => ref.read(addCameraProvider.notifier);

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  Future<void> _addArea() async {
    final area = await showNewAreaSheet(context);
    if (area != null) _flow.selectArea(area.id);
  }

  Future<void> _save(Area area) async {
    final Camera camera;
    try {
      camera = await _flow.save(areaId: area.id);
    } on MpException catch (e) {
      if (mounted) showGroupFailureToast(context, e);
      return;
    }
    if (mounted) context.go(AppRoutes.watch(camera.id));
  }

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final state = ref.watch(addCameraProvider);
    final areas = ref.watch(placeAreasProvider).value ?? const [];
    final selected =
        areas.where((a) => a.id == state.areaId).firstOrNull ??
        areas.firstOrNull;
    final canSave =
        !state.busy && selected != null && state.name.trim().isNotEmpty;
    return MpPage(
      header: MpHeader.back(
        title: 'Đặt tên camera',
        onBack: () => context.pop(),
      ),
      headerBottom: 12,
      gap: 12,
      children: [
        CameraArtBox(
          art: ref.watch(demoSceneArtProvider) ? MpIllustrations.feed : null,
          artSize: _pictureArtSize,
          height: _pictureHeight,
          pictureUrl: state.probe?.previewSnapshotUrl,
        ),
        MpTextField(
          label: 'Tên camera',
          icon: MpIcons.edit,
          controller: _name,
          textInputAction: TextInputAction.done,
          onChanged: _flow.setName,
        ),
        Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          spacing: 8,
          children: [
            Text(
              'Khu vực',
              style: context.mpText.label.copyWith(color: c.textSecondary),
            ),
            MpAreaPicker(
              areas: [for (final a in areas) a.name],
              selected: selected?.name,
              onSelected: (name) =>
                  _flow.selectArea(areas.firstWhere((a) => a.name == name).id),
              onAdd: _addArea,
            ),
          ],
        ),
        const Spacer(),
        MpButton(
          label: 'Lưu',
          onPressed: canSave ? () => _save(selected) : null,
        ),
      ],
    );
  }
}

const _pictureHeight = 170.0;
const _pictureArtSize = Size(317, 317 * 180 / 280);
