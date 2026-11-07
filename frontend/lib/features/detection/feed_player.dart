import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:video_player/video_player.dart';

import '../../core/widgets/mp_still.dart';
import '../../data/models/models.dart';

final feedPlayerProvider = Provider.autoDispose
    .family<VideoPlayerController, FeedSource>((ref, source) {
      final options = VideoPlayerOptions(mixWithOthers: true);
      final controller = source.isNetwork
          ? VideoPlayerController.networkUrl(
              Uri.parse(source.uri),
              formatHint: Uri.parse(source.uri).path.endsWith('.m3u8')
                  ? VideoFormat.hls
                  : null,
              videoPlayerOptions: options,
            )
          : VideoPlayerController.asset(
              source.uri,
              videoPlayerOptions: options,
            );
      var disposed = false;
      ref.onDispose(() {
        disposed = true;
        controller.dispose();
      });
      final end = source.end;
      controller
        ..setVolume(0)
        ..setLooping(end == null);
      if (end != null) {
        loopFeedSegment(
          controller,
          start: source.start,
          end: end,
          disposed: () => disposed,
        );
      }
      controller
          .initialize()
          .then((_) async {
            if (disposed) return;
            if (source.start > Duration.zero) {
              await controller.seekTo(source.start);
            }
            if (!disposed) await controller.play();
          })
          .catchError((Object _) {});
      return controller;
    });

@visibleForTesting
void loopFeedSegment(
  VideoPlayerController controller, {
  required Duration start,
  required Duration end,
  required bool Function() disposed,
}) {
  var rewinding = false;
  Future<void> rewind() async {
    rewinding = true;
    try {
      await controller.seekTo(start);
      if (!disposed()) await controller.play();
    } on Object {
      // Disposed mid-seek, or the clip failed: nothing left to loop.
    } finally {
      rewinding = false;
    }
  }

  controller.addListener(() {
    final value = controller.value;
    if (disposed() || rewinding || !value.isInitialized) return;
    if (value.position >= end || value.isCompleted) unawaited(rewind());
  });
}

class FeedVideo extends ConsumerWidget {
  const FeedVideo({super.key, required this.source, this.still});

  final FeedSource source;

  final String? still;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final controller = ref.watch(feedPlayerProvider(source));
    return ValueListenableBuilder<VideoPlayerValue>(
      valueListenable: controller,
      builder: (context, value, _) {
        final started =
            value.isInitialized &&
            (value.isPlaying || value.position > Duration.zero);
        if (!started || value.hasError) {
          return switch (still) {
            final still? => MpStill(still),
            null => const SizedBox.expand(),
          };
        }
        return FittedBox(
          fit: BoxFit.cover,
          clipBehavior: Clip.hardEdge,
          child: SizedBox.fromSize(
            size: value.size,
            child: VideoPlayer(controller),
          ),
        );
      },
    );
  }
}
