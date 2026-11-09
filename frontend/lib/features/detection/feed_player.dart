import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:video_player/video_player.dart';

import '../../core/widgets/mp_feed_placeholder.dart';
import '../../core/widgets/mp_still.dart';
import '../../data/models/models.dart';
import '../../data/providers.dart';
import 'feed_snapshot.dart';

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
      // A live stream is often missing for a moment: the edge is still connecting a
      // camera that was just added, the tunnel blips, the edge restarts. The player
      // never retries on its own, so rebuild it instead of showing no picture for good.
      final retry = source.isNetwork
          ? retryFeedOnError(
              controller,
              retry: ref.invalidateSelf,
              disposed: () => disposed,
            )
          : () {};
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
          .catchError((Object _) {
            retry();
          });
      return controller;
    });

const feedRetryDelay = Duration(seconds: 3);

/// Calls [retry] once, [delay] after [controller] reports an error.
///
/// Returns a function that schedules the same retry, for failures the controller
/// does not surface in its value (a failed `initialize`). Nothing happens once
/// [disposed] returns true.
@visibleForTesting
void Function() retryFeedOnError(
  VideoPlayerController controller, {
  required void Function() retry,
  required bool Function() disposed,
  Duration delay = feedRetryDelay,
}) {
  var scheduled = false;
  void schedule() {
    if (scheduled || disposed()) return;
    scheduled = true;
    Timer(delay, () {
      if (!disposed()) retry();
    });
  }

  controller.addListener(() {
    if (controller.value.hasError) schedule();
  });
  return schedule;
}

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
  const FeedVideo({super.key, required this.source, this.still, this.snapshot});

  final FeedSource source;

  final ImageProvider? still;

  final FeedSnapshotTarget? snapshot;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final controller = ref.watch(feedPlayerProvider(source));
    final demoArt = ref.watch(demoSceneArtProvider);
    return ValueListenableBuilder<VideoPlayerValue>(
      valueListenable: controller,
      builder: (context, value, _) {
        final started =
            value.isInitialized &&
            (value.isPlaying || value.position > Duration.zero);
        if (!started || value.hasError) {
          final Widget fallback = demoArt
              ? const SizedBox.expand()
              : MpFeedPlaceholder(
                  caption: value.hasError
                      ? 'Không có hình trực tiếp'
                      : 'Đang tải hình…',
                );
          return switch (still) {
            final still? => MpStill.image(still, fallback: fallback),
            null => fallback,
          };
        }
        final video = FittedBox(
          fit: BoxFit.cover,
          clipBehavior: Clip.hardEdge,
          child: SizedBox.fromSize(
            size: value.size,
            child: VideoPlayer(controller),
          ),
        );
        return switch (snapshot) {
          final target? => FeedSnapshotBoundary(target: target, child: video),
          null => video,
        };
      },
    );
  }
}
