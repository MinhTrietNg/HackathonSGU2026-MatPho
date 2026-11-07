library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import '../../core/theme/mp_overlay_colors.dart';
import '../../core/theme/theme.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_feed_tag.dart';
import '../../core/widgets/mp_illustration.dart';
import '../../data/providers.dart';
import '../cameras/camera_state.dart';
import 'detection_controller.dart';
import 'watch_widgets.dart';

class WatchFullScreen extends ConsumerWidget {
  const WatchFullScreen({super.key, required this.cameraId});

  final String cameraId;

  void _close(BuildContext context) {
    if (context.canPop()) {
      context.pop();
    } else {
      context.go(AppRoutes.watch(cameraId));
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final camera = ref.watch(watchCameraProvider(cameraId)).value;
    final art = watchArtOf(ref.watch(detectionControllerProvider(cameraId)));
    final clock = ref.watch(clockProvider);
    final place = (camera?.areaName ?? camera?.camera.name ?? '').toUpperCase();
    final chipText = context.mpText.mono.copyWith(
      fontSize: 13,
      fontWeight: FontWeight.w600,
      height: kTextHeightNone,
      color: MpOverlayColors.onFeed,
    );
    return Scaffold(
      backgroundColor: MpOverlayColors.fullScreen,
      body: RotatedBox(
        quarterTurns: 1,
        child: LayoutBuilder(
          builder: (context, box) {
            final aspect =
                MpIllustration.figmaSize.width /
                MpIllustration.figmaSize.height;
            return Stack(
              children: [
                Center(
                  child: SizedBox(
                    width: box.maxHeight * aspect,
                    height: box.maxHeight,
                    child: ClipRect(
                      child: WatchFeedPicture(
                        art: art,
                        video: camera == null
                            ? null
                            : ref.watch(cameraFeedProvider(camera.camera)),
                        still: ref.watch(cameraStillProvider(cameraId)),
                      ),
                    ),
                  ),
                ),
                Positioned(
                  left: 24,
                  top: 20,
                  child: WatchTicker(
                    clock: clock,
                    builder: (now) => MpFeedTag(
                      '$place · ${formatFeedTime(now)}',
                      style: chipText,
                    ),
                  ),
                ),
                Positioned(
                  right: 24,
                  top: 16,
                  child: Semantics(
                    button: true,
                    label: 'Thoát toàn màn hình',
                    excludeSemantics: true,
                    child: GestureDetector(
                      behavior: HitTestBehavior.opaque,
                      onTap: () => _close(context),
                      child: Container(
                        width: 44,
                        height: 44,
                        alignment: Alignment.center,
                        decoration: const BoxDecoration(
                          color: MpOverlayColors.fullScreenChip,
                          shape: BoxShape.circle,
                        ),
                        child: const MpDuotoneIcon(
                          MpIcons.close,
                          outline: MpOverlayColors.onFeed,
                          accent: MpOverlayColors.onFeed,
                          size: 22,
                        ),
                      ),
                    ),
                  ),
                ),
                Positioned(
                  right: 24,
                  bottom: 20,
                  child: _Chip('Chạm × để thoát', chipText),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _Chip extends StatelessWidget {
  const _Chip(this.text, this.style);

  static const _padding = EdgeInsets.symmetric(horizontal: 10, vertical: 5);
  static const _radius = 8.0;

  final String text;
  final TextStyle style;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: _padding,
      decoration: BoxDecoration(
        color: MpOverlayColors.fullScreenChip,
        borderRadius: BorderRadius.circular(_radius),
      ),
      child: Text(text, maxLines: 1, style: style),
    );
  }
}
