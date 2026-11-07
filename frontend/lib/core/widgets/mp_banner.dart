import 'dart:async';

import 'package:flutter/material.dart';

import '../theme/theme.dart';
import 'mp_duotone_icon.dart';

enum MpBannerTone { fire, warn, accent, ok }

class MpBanner extends StatelessWidget {
  const MpBanner({
    super.key,
    required this.tone,
    this.icon,
    this.thumbnail,
    required this.title,
    this.body,
    this.outlined = true,
    this.actionLabel,
    this.onAction,
  }) : assert(icon == null || thumbnail == null);

  final MpBannerTone tone;

  final String? icon;

  final Widget? thumbnail;

  final String title;
  final String? body;
  final bool outlined;
  final String? actionLabel;
  final VoidCallback? onAction;

  static const thumbnailArtSize = Size(81, 81 * 180 / 280);

  static const _thumbnailSize = Size(72, 52);

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final (fill, border, glyph) = switch (tone) {
      MpBannerTone.fire => (c.statusFireSoft, c.statusFire, c.statusFire),
      MpBannerTone.warn => (c.statusWarnSoft, c.statusWarn, c.statusWarn),
      MpBannerTone.accent => (c.bgCard, c.brandAccent, c.brandAccentFg),
      MpBannerTone.ok => (c.statusOkSoft, c.statusOk, c.statusOk),
    };
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: fill,
        border: Border.all(color: outlined ? border : Colors.transparent),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        crossAxisAlignment: thumbnail == null
            ? CrossAxisAlignment.start
            : CrossAxisAlignment.center,
        spacing: 12,
        children: [
          if (icon case final icon?)
            MpDuotoneIcon(icon, outline: glyph, accent: glyph, size: 22),
          if (thumbnail case final thumbnail?)
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
                if (body case final body?)
                  Text(
                    body,
                    style: t.caption.copyWith(
                      fontWeight: FontWeight.w500,
                      color: c.textSecondary,
                    ),
                  ),
              ],
            ),
          ),
          if (actionLabel case final label?)
            Semantics(
              button: true,
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: onAction,
                child: Text(
                  label,
                  style: t.label.copyWith(color: c.brandAccentFg),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class MpAlertBanner extends StatelessWidget {
  const MpAlertBanner({
    super.key,
    this.icon = MpIcons.flame,
    required this.title,
    this.subtitle,
    this.onTap,
  });

  final String icon;
  final String title;
  final String? subtitle;
  final VoidCallback? onTap;

  static const duration = Duration(milliseconds: 240);

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final fg = c.onStatusFromLight;
    return Semantics(
      liveRegion: true,
      container: true,
      button: onTap != null,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () {
          onTap?.call();
          _AlertBannerScope.maybeOf(context)?.dismiss();
        },
        child: Container(
          padding: const EdgeInsets.fromLTRB(12, 10, 10, 10),
          decoration: BoxDecoration(
            color: c.statusFire,
            borderRadius: BorderRadius.circular(16),
            boxShadow: [
              BoxShadow(
                color: c.bannerShadow,
                offset: Offset(0, 6),
                blurRadius: 16,
              ),
            ],
          ),
          child: Row(
            spacing: 12,
            children: [
              Container(
                width: 34,
                height: 34,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: c.bgBase,
                  shape: BoxShape.circle,
                ),
                child: MpDuotoneIcon(
                  icon,
                  outline: c.textPrimary,
                  accent: c.textPrimary,
                  size: 22,
                ),
              ),
              Expanded(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      title,
                      style: t.headline.copyWith(
                        fontWeight: FontWeight.w700,
                        color: fg,
                      ),
                    ),
                    if (subtitle case final subtitle?)
                      Text(
                        subtitle,
                        style: t.caption.copyWith(
                          fontWeight: FontWeight.w500,
                          color: fg,
                        ),
                      ),
                  ],
                ),
              ),
              MpDuotoneIcon(MpIcons.chevron, outline: fg, accent: fg, size: 20),
            ],
          ),
        ),
      ),
    );
  }
}

void showMpAlertBanner(
  BuildContext context,
  MpAlertBanner banner, {
  Duration? duration,
}) {
  _current?.dismiss();
  final entry = _BannerEntry(banner);
  _current = entry;
  entry.insert(Overlay.of(context, rootOverlay: true), duration);
}

void hideMpAlertBanner() => _current?.dismiss();

_BannerEntry? _current;

class _BannerEntry {
  _BannerEntry(this.banner);

  final MpAlertBanner banner;
  final _layerKey = GlobalKey<_BannerLayerState>();
  late final _overlayEntry = OverlayEntry(
    builder: (_) => _AlertBannerScope(
      entry: this,
      child: _BannerLayer(key: _layerKey, child: banner),
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

class _AlertBannerScope extends InheritedWidget {
  const _AlertBannerScope({required this.entry, required super.child});

  final _BannerEntry entry;

  static _BannerEntry? maybeOf(BuildContext context) =>
      context.getInheritedWidgetOfExactType<_AlertBannerScope>()?.entry;

  @override
  bool updateShouldNotify(_AlertBannerScope oldWidget) =>
      entry != oldWidget.entry;
}

class _BannerLayer extends StatefulWidget {
  const _BannerLayer({super.key, required this.child});

  final Widget child;

  @override
  State<_BannerLayer> createState() => _BannerLayerState();
}

class _BannerLayerState extends State<_BannerLayer>
    with SingleTickerProviderStateMixin {
  late final _controller = AnimationController(
    vsync: this,
    duration: MpAlertBanner.duration,
  )..forward();

  late final _offset = _controller.drive(
    Tween(
      begin: const Offset(0, -2.5),
      end: Offset.zero,
    ).chain(CurveTween(curve: Curves.easeOut)),
  );

  Future<void> exit() => _controller.reverse().orCancel.catchError((_) {});

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Positioned(
      top: MediaQuery.paddingOf(context).top + 12,
      left: 20,
      right: 20,
      child: SlideTransition(
        position: _offset,
        child: GestureDetector(
          onVerticalDragEnd: (details) {
            if ((details.primaryVelocity ?? 0) < 0) {
              _AlertBannerScope.maybeOf(context)?.dismiss();
            }
          },
          child: Material(type: MaterialType.transparency, child: widget.child),
        ),
      ),
    );
  }
}
