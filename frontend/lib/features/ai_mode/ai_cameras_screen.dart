library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import '../../core/theme/theme.dart';
import '../../core/widgets/mp_chip.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_header.dart';
import '../../core/widgets/mp_page.dart';
import '../../core/widgets/mp_section_label.dart';
import '../../core/widgets/mp_settings_row.dart';
import '../../data/models/models.dart';
import '../groups/group_state.dart';
import 'ai_mode_routes.dart';
import 'ai_mode_state.dart';
import 'ai_mode_widgets.dart';

class AiCamerasScreen extends ConsumerStatefulWidget {
  const AiCamerasScreen({super.key});

  @override
  ConsumerState<AiCamerasScreen> createState() => _AiCamerasScreenState();
}

class _AiCamerasScreenState extends ConsumerState<AiCamerasScreen> {
  String? _picked;
  AiCamerasView? _shown;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    // Keeps the last group on screen while a newly picked one loads.
    final shown = _shown =
        ref.watch(aiCamerasViewProvider(_picked)).value ?? _shown;
    final groups = shown?.groups ?? const <Group>[];
    final view = shown?.selected;
    final selectedId = _picked ?? view?.group.id;

    return MpPage(
      header: MpHeader.back(
        title: 'AI nhận diện cháy',
        onBack: () =>
            context.canPop() ? context.pop() : context.go(AppRoutes.settings),
      ),
      headerBottom: 14,
      gap: 14,
      children: [
        if (groups.length > 1)
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              for (final g in groups)
                MpChip(
                  label: shortGroupName(groupDisplayName(g)),
                  style: MpChipStyle.filled,
                  selected: g.id == selectedId,
                  onTap: () => setState(() => _picked = g.id),
                ),
            ],
          ),
        if (view != null) ...[
          AiCountCard(
            count: view.cameras.length,
            subtitle:
                '${groupDisplayName(view.group)} · '
                'bạn là ${aiRolePhrase(view.group.myRole)}',
          ),
          if (!view.group.myRole.canManage)
            AiLockedNote(ownerName: view.ownerName),
          MpSectionLabel('CAMERA · ${view.cameras.length}'),
          if (view.cameras.isNotEmpty)
            MpSettingsGroup(
              children: [
                for (final camera in view.cameras)
                  _CameraRow(
                    camera: camera,
                    locked: !view.group.myRole.canManage,
                  ),
              ],
            ),
          if (view.group.myRole.canManage && view.cameras.isNotEmpty)
            Text(
              'Chạm vào camera để hẹn giờ nghỉ AI, ví dụ giờ nấu ăn ở bếp. '
              'Ngoài giờ đó AI vẫn báo cháy.',
              style: t.caption.copyWith(
                fontWeight: FontWeight.w500,
                color: c.textMuted,
              ),
            ),
        ],
        const Spacer(),
      ],
    );
  }
}

class _CameraRow extends StatelessWidget {
  const _CameraRow({required this.camera, required this.locked});

  final Camera camera;
  final bool locked;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final off = camera.ai.mode == AiMode.off;
    return MpSettingsRow(
      icon: MpIcons.camera,
      iconColor: off ? c.textMuted : c.brandAccent,
      title: camera.name,
      subtitle: aiModeSummary(camera.ai, locked: locked),
      subtitleColor: switch (camera.ai.mode) {
        AiMode.alwaysOn => null,
        AiMode.scheduled => c.brandAccentFg,
        AiMode.off => c.statusWarn,
      },
      trailing: locked
          ? MpDuotoneIcon(
              MpIcons.lock,
              outline: c.textMuted,
              accent: c.textMuted,
              size: 18,
            )
          : null,
      onTap: locked ? null : () => context.push(AiModeRoutes.camera(camera.id)),
    );
  }
}
