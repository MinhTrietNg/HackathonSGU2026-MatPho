import 'dart:async';

import 'package:flutter/material.dart';

import '../theme/theme.dart';
import 'mp_tab_bar.dart';

class MpToast extends StatelessWidget {
  const MpToast({
    super.key,
    this.icon,
    required this.title,
    this.actionLabel,
    this.onAction,
  }) : thumbnail = null,
       subtitle = null;

  const MpToast.rich({
    super.key,
    required Widget this.thumbnail,
    required this.title,
    this.subtitle,
    this.actionLabel,
    this.onAction,
  }) : icon = null;

  final Widget? icon;

  final Widget? thumbnail;

  final String title;
  final String? subtitle;
  final String? actionLabel;
  final VoidCallback? onAction;

  static const dismissedDuration = Duration(seconds: 4);

  static const undoDuration = Duration(seconds: 5);

  static const thumbnailArtSize = Size(72, 72 * 180 / 280);

  static const defaultBottom = MpTabBar.height + 12;

  static const maxWidth = 320.0;

  static const enterDuration = Duration(milliseconds: 200);
  static const exitDuration = Duration(milliseconds: 150);

  static const _thumbnailSize = Size(72, 46);

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final rich = thumbnail != null;

    void act() {
      onAction?.call();
      _MpToastScope.maybeOf(context)?.dismiss();
    }

    Widget? action;
    if (actionLabel case final label?) {
      action = Text(label, style: t.label.copyWith(color: c.brandAccentFg));
      if (!rich) {
        action = Semantics(
          button: true,
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: act,
            child: action,
          ),
        );
      }
    }

    final Widget content;
    if (rich) {
      content = Row(
        spacing: 12,
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(10),
            child: SizedBox.fromSize(
              size: _thumbnailSize,
              child: OverflowBox(
                maxWidth: double.infinity,
                maxHeight: double.infinity,
                child: thumbnail,
              ),
            ),
          ),
          Expanded(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              spacing: 2,
              children: [
                Text(
                  title,
                  style: t.body.copyWith(
                    fontWeight: FontWeight.w700,
                    color: c.textPrimary,
                  ),
                ),
                if (subtitle case final subtitle?)
                  Text(
                    subtitle,
                    style: t.caption.copyWith(
                      fontWeight: FontWeight.w500,
                      color: c.textSecondary,
                    ),
                  ),
              ],
            ),
          ),
          ?action,
        ],
      );
    } else {
      content = Row(
        spacing: 10,
        children: [
          if (icon case final icon?)
            SizedBox.square(dimension: 18, child: icon),
          Expanded(
            child: Text(
              title,
              style: t.body.copyWith(
                fontWeight: FontWeight.w500,
                color: c.textPrimary,
              ),
            ),
          ),
          ?action,
        ],
      );
    }

    Widget toast = Container(
      padding: rich
          ? const EdgeInsets.all(12)
          : const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: c.bgRaised,
        borderRadius: BorderRadius.circular(14),
      ),
      child: content,
    );
    if (rich && onAction != null) {
      toast = Semantics(
        button: true,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: act,
          child: toast,
        ),
      );
    }
    return Semantics(liveRegion: true, container: true, child: toast);
  }
}

void showMpToast(
  BuildContext context,
  MpToast toast, {
  Duration? duration = MpToast.undoDuration,
  double bottom = MpToast.defaultBottom,
}) {
  final overlay = Overlay.of(context, rootOverlay: true);
  _current?.dismiss();
  final entry = _ToastEntry(toast: toast, bottom: bottom);
  entry.insert(overlay, duration);
  _current = entry;
}

void hideMpToast() {
  _current?.dismiss();
}

_ToastEntry? _current;

class _ToastEntry {
  _ToastEntry({required this.toast, required this.bottom});

  final MpToast toast;
  final double bottom;
  final _layerKey = GlobalKey<_ToastLayerState>();
  late final _overlayEntry = OverlayEntry(
    builder: (_) => _MpToastScope(
      entry: this,
      child: _ToastLayer(key: _layerKey, bottom: bottom, child: toast),
    ),
  );
  Timer? _timer;
  bool _dismissed = false;

  void insert(OverlayState overlay, Duration? duration) {
    overlay.insert(_overlayEntry);
    if (duration != null) _timer = Timer(duration, dismiss);
  }

  Future<void> dismiss() async {
    if (_dismissed) return;
    _dismissed = true;
    _timer?.cancel();
    if (identical(_current, this)) _current = null;
    await _layerKey.currentState?.exit();
    _overlayEntry
      ..remove()
      ..dispose();
  }
}

class _MpToastScope extends InheritedWidget {
  const _MpToastScope({required this.entry, required super.child});

  final _ToastEntry entry;

  static _ToastEntry? maybeOf(BuildContext context) =>
      context.getInheritedWidgetOfExactType<_MpToastScope>()?.entry;

  @override
  bool updateShouldNotify(_MpToastScope oldWidget) => entry != oldWidget.entry;
}

class _ToastLayer extends StatefulWidget {
  const _ToastLayer({super.key, required this.bottom, required this.child});

  final double bottom;
  final Widget child;

  @override
  State<_ToastLayer> createState() => _ToastLayerState();
}

class _ToastLayerState extends State<_ToastLayer>
    with SingleTickerProviderStateMixin {
  late final _controller = AnimationController(
    vsync: this,
    duration: MpToast.enterDuration,
    reverseDuration: MpToast.exitDuration,
  )..forward();

  late final _opacity = _controller.drive(CurveTween(curve: Curves.easeOut));

  Future<void> exit() => _controller.reverse().orCancel.catchError((_) {});

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Positioned(
      left: 16,
      right: 16,
      bottom: widget.bottom + MediaQuery.paddingOf(context).bottom,
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: MpToast.maxWidth),
          child: FadeTransition(
            opacity: _opacity,
            child: Material(
              type: MaterialType.transparency,
              child: widget.child,
            ),
          ),
        ),
      ),
    );
  }
}
