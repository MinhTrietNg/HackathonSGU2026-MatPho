library;

import 'package:flutter/material.dart';

import '../../core/theme/theme.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_sheet.dart';
import '../../data/models/camera.dart';
import 'camera_widgets.dart';

enum CameraSheetAction { removeRtsp, delete }

// I20: what an owner or manager can do to a camera, from the trash button on
// E2 and I8. The link is already gone on a camera without RTSP.
Future<CameraSheetAction?> showCameraActionsSheet(
  BuildContext context,
  Camera camera,
) => showMpSheet<CameraSheetAction>(
  context,
  builder: (_) => CameraActionsSheet(camera: camera),
);

class CameraActionsSheet extends StatelessWidget {
  const CameraActionsSheet({super.key, required this.camera});

  final Camera camera;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    void pick(CameraSheetAction action) => Navigator.of(context).pop(action);
    return CameraSheet(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 32),
      spacing: 10,
      handleColor: c.lineSubtle,
      centerHandle: false,
      children: [
        Semantics(
          header: true,
          child: Text(
            camera.name,
            style: context.mpText.title.copyWith(
              fontSize: 18,
              fontWeight: FontWeight.w800,
              height: normalHeight(18),
              color: c.textPrimary,
            ),
          ),
        ),
        if (camera.hasRtsp)
          _ActionRow(
            icon: MpIcons.wifiOff,
            title: 'Gỡ đường dẫn RTSP',
            detail: 'AI ngừng quét. Giữ tên, khu vực và lịch sử.',
            onTap: () => pick(CameraSheetAction.removeRtsp),
          ),
        _ActionRow(
          icon: MpIcons.trash,
          title: 'Xoá camera',
          detail: 'Vào thùng rác, khôi phục được trong 30 ngày.',
          danger: true,
          onTap: () => pick(CameraSheetAction.delete),
        ),
      ],
    );
  }
}

class _ActionRow extends StatelessWidget {
  const _ActionRow({
    required this.icon,
    required this.title,
    required this.detail,
    required this.onTap,
    this.danger = false,
  });

  final String icon;
  final String title;
  final String detail;
  final VoidCallback onTap;
  final bool danger;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final tint = danger ? c.statusFire : c.textPrimary;
    return Semantics(
      button: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          decoration: BoxDecoration(
            color: c.bgCard,
            borderRadius: BorderRadius.circular(16),
          ),
          child: Row(
            spacing: 12,
            children: [
              Container(
                width: 40,
                height: 40,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: c.bgRaised,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: MpDuotoneIcon(
                  icon,
                  outline: tint,
                  accent: danger ? c.statusFire : c.brandAccent,
                  size: 22,
                ),
              ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  spacing: 2,
                  children: [
                    Text(
                      title,
                      style: t.body.copyWith(
                        fontWeight: FontWeight.w700,
                        color: tint,
                      ),
                    ),
                    Text(
                      detail,
                      style: t.label.copyWith(color: c.textSecondary),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
