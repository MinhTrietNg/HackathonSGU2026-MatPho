library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import '../../core/theme/theme.dart';
import '../../core/time_format.dart';
import '../../core/widgets/mp_badge.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_icon_button.dart';
import '../../core/widgets/mp_illustration.dart';
import '../../core/widgets/mp_list_card.dart';
import '../../core/widgets/mp_section_label.dart';
import '../../core/widgets/mp_still.dart';
import '../../core/widgets/mp_toast.dart';
import '../../data/models/models.dart';
import '../../data/providers.dart';
import '../auth/notifications_off_banner.dart';
import '../auth/permission_controller.dart';
import '../groups/group_state.dart' show groupDisplayName, roleLabel;
import 'camera_routes.dart';
import 'camera_state.dart';
import 'camera_widgets.dart';
import 'place_picker_sheet.dart';

class CameraMonitorScreen extends ConsumerWidget {
  const CameraMonitorScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final place = ref.watch(currentPlaceProvider).value;
    final sections = ref.watch(placeCamerasProvider).value;
    ref.watch(cameraPlacesProvider);
    final canManage = place?.myRole.canManage ?? false;
    final notificationsOff =
        ref.watch(notificationPermissionProvider).value ==
        NotificationPermission.denied;
    void addCamera() {
      ref.read(addCameraProvider.notifier).start();
      context.push(CameraRoutes.add);
    }

    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: Stack(
          children: [
            Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(20, 7, 20, 10),
                  child: _PlaceTitle(
                    name: place == null ? null : groupDisplayName(place),
                    trailingSlot: canManage || place == null ? 50 : 82,
                    onTap: () => showPlacePicker(context),
                  ),
                ),
                if (sections == null)
                  const Spacer()
                else
                  Expanded(
                    child: SingleChildScrollView(
                      padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        spacing: 10,
                        children: [
                          if (notificationsOff) const NotificationsOffBanner(),
                          for (final section in sections) ...[
                            if (section.area case final area?)
                              _AreaHeader(
                                name: area.name,
                                cameras: section.cameras,
                                assigned: !canManage,
                              ),
                            for (final camera in section.cameras)
                              _CameraRow(
                                camera,
                                canWatch: place?.myRole.canWatch ?? false,
                              ),
                          ],
                          if (canManage) _AddCameraCard(onTap: addCamera),
                        ],
                      ),
                    ),
                  ),
              ],
            ),
            if (place != null && canManage)
              Positioned(
                top: 7,
                right: 18,
                child: MpIconButton(
                  icon: MpIcons.plus,
                  semanticLabel: 'Thêm camera',
                  accent: true,
                  onPressed: addCamera,
                ),
              )
            else if (place != null)
              Positioned(
                top: 18,
                right: 16,
                child: _RolePill(roleLabel(place.myRole)),
              ),
          ],
        ),
      ),
    );
  }
}

class _PlaceTitle extends StatelessWidget {
  const _PlaceTitle({
    required this.name,
    required this.trailingSlot,
    required this.onTap,
  });

  final String? name;
  final double trailingSlot;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final name = this.name;
    return SizedBox(
      height: 40,
      child: name == null
          ? null
          : Row(
              children: [
                Flexible(
                  child: Padding(
                    padding: EdgeInsetsDirectional.only(end: trailingSlot),
                    child: Semantics(
                      button: true,
                      header: true,
                      label: 'Chọn nơi: $name',
                      excludeSemantics: true,
                      child: GestureDetector(
                        behavior: HitTestBehavior.opaque,
                        onTap: onTap,
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          spacing: 6,
                          children: [
                            Flexible(
                              child: Text(
                                name,
                                maxLines: 1,
                                softWrap: false,
                                overflow: TextOverflow.ellipsis,
                                style: context.mpText.title.copyWith(
                                  fontWeight: FontWeight.w800,
                                  height: 1.4,
                                  color: c.textPrimary,
                                ),
                              ),
                            ),
                            RotatedBox(
                              quarterTurns: 1,
                              child: MpScaledIcon(
                                MpIcons.chevron,
                                color: c.textSecondary,
                                size: 22,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
    );
  }
}

class _RolePill extends StatelessWidget {
  const _RolePill(this.label);

  final String label;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: c.bgRaised,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: context.mpText.label.copyWith(
          fontSize: 11,
          height: normalHeight(11),
          color: c.textSecondary,
        ),
      ),
    );
  }
}

class _AreaHeader extends StatelessWidget {
  const _AreaHeader({
    required this.name,
    required this.cameras,
    required this.assigned,
  });

  final String name;
  final List<Camera> cameras;
  final bool assigned;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final style = context.mpText.caption.copyWith(
      fontWeight: FontWeight.w500,
      color: c.textSecondary,
    );
    final lost = cameras
        .where((cam) => cam.status == CameraStatus.signalLost)
        .length;
    return Padding(
      padding: const EdgeInsets.only(top: 6),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          MpSectionLabel(name.toUpperCase()),
          Row(
            spacing: 6,
            children: [
              Text(
                '${cameras.length} camera${assigned ? ' được giao' : ''}',
                style: style,
              ),
              if (lost > 0) Text('· $lost mất tín hiệu', style: style),
            ],
          ),
        ],
      ),
    );
  }
}

const _thumbnailArtSize = Size(75, 75 * 180 / 280);

class _CameraRow extends ConsumerWidget {
  const _CameraRow(this.camera, {required this.canWatch});

  final Camera camera;

  final bool canWatch;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final lost = camera.status == CameraStatus.signalLost;
    final since = camera.signalLostSince;
    final still = lost ? null : ref.watch(cameraStillProvider(camera.id));
    return MpListCard(
      thumbnail: switch (still) {
        final still? => MpStill(still, size: MpListCard.thumbnailSize),
        null when lost => const MpIllustration(
          MpIllustrations.camOffline,
          size: _thumbnailArtSize,
          backdrop: false,
        ),
        null => const MpIllustration(
          MpIllustrations.feed,
          size: _thumbnailArtSize,
        ),
      },
      title: camera.name,
      subtitle: lost && since != null
          ? 'Mất tín hiệu từ ${formatClock(since, seconds: false)}'
          : 'AI đang quét',
      badge: lost
          ? const MpBadge(label: 'Mất tín hiệu', tone: MpBadgeTone.warn)
          : const MpBadge(label: 'Đang theo dõi', tone: MpBadgeTone.live),
      trailing: canWatch ? const MpChevron() : null,
      onTap: canWatch
          ? () => context.push(
              lost
                  ? CameraRoutes.signalLost(camera.id)
                  : AppRoutes.watch(camera.id),
            )
          : () => showMpToast(context, const MpToast(title: noLiveViewNote)),
    );
  }
}

class _AddCameraCard extends StatelessWidget {
  const _AddCameraCard({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    return MpListCard(
      dashed: true,
      thumbnail: MpDuotoneIcon(
        MpIcons.camera,
        outline: c.textPrimary,
        accent: c.brandAccent,
      ),
      title: 'Thêm camera RTSP',
      subtitle: 'Dán đường dẫn RTSP · AI quét 24/7',
      onTap: onTap,
    );
  }
}
