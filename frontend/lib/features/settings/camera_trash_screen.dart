library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import '../../core/theme/theme.dart';
import '../../core/widgets/mp_banner.dart';
import '../../core/widgets/mp_button.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_header.dart';
import '../../core/widgets/mp_illustration.dart';
import '../../core/widgets/mp_page.dart';
import '../../core/widgets/mp_settings_row.dart';
import '../../data/errors.dart';
import '../../data/models/models.dart';
import '../../data/providers.dart';
import '../cameras/camera_actions.dart';
import '../cameras/camera_dialogs.dart';

// I18: cameras deleted in the last 30 days, per place. Owners and managers
// restore; only the owner deletes for good.
class CameraTrashScreen extends ConsumerStatefulWidget {
  const CameraTrashScreen({super.key});

  @override
  ConsumerState<CameraTrashScreen> createState() => _CameraTrashScreenState();
}

class _CameraTrashScreenState extends ConsumerState<CameraTrashScreen> {
  String? _busyId;

  static const _artSize = Size(200, 200 * 180 / 280);

  Future<void> _run(String cameraId, Future<void> Function() action) async {
    setState(() => _busyId = cameraId);
    try {
      await action();
    } on MpException {
      if (mounted) showCameraActionFailedToast(context);
    } finally {
      if (mounted) setState(() => _busyId = null);
    }
  }

  Future<void> _restore(TrashedCamera camera) => _run(
    camera.id,
    () => ref.read(cameraActionsProvider).restore(camera.id),
  );

  Future<void> _deleteForever(TrashedCamera camera) async {
    if (!await confirmDeleteCameraForever(context, camera.name) || !mounted) {
      return;
    }
    await _run(
      camera.id,
      () => ref.read(cameraActionsProvider).deleteForever(camera.id),
    );
  }

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final trash = ref.watch(cameraTrashProvider);
    final now = ref.watch(clockProvider)();
    return MpPage(
      header: MpHeader.back(
        title: 'Camera đã xoá',
        onBack: () =>
            context.canPop() ? context.pop() : context.go(AppRoutes.settings),
      ),
      headerBottom: 14,
      gap: 14,
      onRefresh: () => ref.refresh(cameraTrashProvider.future).then((_) {}),
      children: switch (trash) {
        AsyncValue(:final value?) when value.isEmpty => [
          const Spacer(),
          const Center(
            child: MpIllustration(MpIllustrations.delete, size: _artSize),
          ),
          Column(
            spacing: 8,
            children: [
              Text(
                'Chưa xoá camera nào',
                textAlign: TextAlign.center,
                style: t.title.copyWith(
                  fontWeight: FontWeight.w800,
                  color: c.textPrimary,
                ),
              ),
              Text(
                'Camera đã xoá nằm ở đây 30 ngày rồi mới mất hẳn.',
                textAlign: TextAlign.center,
                style: t.body.copyWith(
                  fontWeight: FontWeight.w500,
                  color: c.textSecondary,
                ),
              ),
            ],
          ),
          const Spacer(flex: 2),
        ],
        AsyncValue(:final value?) => [
          for (final place in value) ...[
            Text(
              place.group.name,
              style: t.label.copyWith(color: c.textSecondary),
            ),
            for (final camera in place.cameras)
              _TrashedCameraCard(
                camera: camera,
                daysLeft: _daysLeft(camera, now),
                busy: _busyId == camera.id,
                canPurge: place.group.myRole == GroupRole.owner,
                onRestore: () => unawaited(_restore(camera)),
                onDeleteForever: () => unawaited(_deleteForever(camera)),
              ),
          ],
        ],
        AsyncValue(hasError: true) => const [
          MpBanner(
            tone: MpBannerTone.warn,
            icon: MpIcons.wifiOff,
            title: 'Không tải được danh sách',
            body: 'Kiểm tra kết nối rồi kéo xuống để thử lại.',
          ),
        ],
        _ => const [],
      },
    );
  }
}

int? _daysLeft(TrashedCamera camera, DateTime now) {
  final purgeAt = camera.purgeAt;
  if (purgeAt == null) return null;
  final left = purgeAt.difference(now);
  return left.isNegative ? 0 : (left.inHours / 24).ceil();
}

class _TrashedCameraCard extends StatelessWidget {
  const _TrashedCameraCard({
    required this.camera,
    required this.daysLeft,
    required this.busy,
    required this.canPurge,
    required this.onRestore,
    required this.onDeleteForever,
  });

  final TrashedCamera camera;
  final int? daysLeft;
  final bool busy;
  final bool canPurge;
  final VoidCallback onRestore;
  final VoidCallback onDeleteForever;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final where = [
      ?camera.areaName,
      if (daysLeft != null) 'còn $daysLeft ngày',
    ].join(' · ');
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      spacing: 8,
      children: [
        MpSettingsGroup(
          children: [
            MpSettingsRow(
              icon: MpIcons.camera,
              iconColor: c.textSecondary,
              title: camera.name,
              subtitle: where.isEmpty ? null : where,
            ),
          ],
        ),
        Row(
          spacing: 10,
          children: [
            Expanded(
              child: MpButton(
                label: 'Khôi phục',
                kind: MpButtonKind.secondary,
                size: MpButtonSize.m,
                icon: MpIcons.history,
                onPressed: busy ? null : onRestore,
              ),
            ),
            if (canPurge)
              Expanded(
                child: MpButton(
                  label: 'Xoá hẳn',
                  kind: MpButtonKind.ghost,
                  size: MpButtonSize.m,
                  icon: MpIcons.trash,
                  onPressed: busy ? null : onDeleteForever,
                ),
              ),
          ],
        ),
      ],
    );
  }
}
