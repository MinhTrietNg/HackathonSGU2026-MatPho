import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../theme/theme.dart';

class MpDuotoneIcon extends StatelessWidget {
  const MpDuotoneIcon(
    this.asset, {
    super.key,
    required this.outline,
    required this.accent,
    this.size = 24,
  });

  final String asset;
  final Color outline;
  final Color accent;
  final double size;

  static const _exportSize = 24.0;

  @override
  Widget build(BuildContext context) {
    final mapper = _DuotoneColorMapper(
      asset: asset,
      outline: outline,
      accent: accent,
    );
    return SvgPicture(
      size == _exportSize
          ? SvgAssetLoader(asset, colorMapper: mapper)
          : _FixedStrokeLoader(
              asset,
              strokeScale: _exportSize / size,
              colorMapper: mapper,
            ),
      width: size,
      height: size,
    );
  }
}

class MpChevron extends StatelessWidget {
  const MpChevron({super.key});

  @override
  Widget build(BuildContext context) {
    final muted = context.mpColors.textMuted;
    return MpDuotoneIcon(
      MpIcons.chevron,
      outline: muted,
      accent: muted,
      size: 18,
    );
  }
}

class MpScaledIcon extends StatelessWidget {
  const MpScaledIcon(
    this.asset, {
    super.key,
    required this.color,
    required this.size,
  });

  final String asset;
  final Color color;
  final double size;

  @override
  Widget build(BuildContext context) {
    return SizedBox.square(
      dimension: size,
      child: FittedBox(
        child: MpDuotoneIcon(asset, outline: color, accent: color),
      ),
    );
  }
}

@immutable
class _FixedStrokeLoader extends SvgAssetLoader {
  const _FixedStrokeLoader(
    super.assetName, {
    required this.strokeScale,
    super.colorMapper,
  });

  final double strokeScale;

  static final _strokeWidth = RegExp(r'stroke-width="([0-9.]+)"');

  @override
  String provideSvg(ByteData? message) => super
      .provideSvg(message)
      .replaceAllMapped(
        _strokeWidth,
        (m) => 'stroke-width="${double.parse(m[1]!) * strokeScale}"',
      );

  @override
  SvgCacheKey cacheKey(BuildContext? context) => SvgCacheKey(
    theme: getTheme(context),
    colorMapper: colorMapper,
    keyData: (assetName, strokeScale),
  );

  @override
  bool operator ==(Object other) =>
      other is _FixedStrokeLoader &&
      super == other &&
      other.strokeScale == strokeScale;

  @override
  int get hashCode => Object.hash(super.hashCode, strokeScale);
}

abstract final class MpIcons {
  static const eye = 'assets/icons/eye.svg';
  static const history = 'assets/icons/history.svg';
  static const settings = 'assets/icons/settings.svg';
  static const plus = 'assets/icons/plus.svg';
  static const play = 'assets/icons/play.svg';
  static const stop = 'assets/icons/stop.svg';
  static const call = 'assets/icons/call.svg';
  static const flag = 'assets/icons/flag.svg';
  static const check = 'assets/icons/check.svg';
  static const shield = 'assets/icons/shield.svg';
  static const bell = 'assets/icons/bell.svg';
  static const battery = 'assets/icons/battery.svg';
  static const upload = 'assets/icons/upload.svg';
  static const film = 'assets/icons/film.svg';
  static const camera = 'assets/icons/camera.svg';
  static const lock = 'assets/icons/lock.svg';
  static const key = 'assets/icons/key.svg';
  static const phone = 'assets/icons/phone.svg';
  static const sms = 'assets/icons/sms.svg';
  static const logout = 'assets/icons/logout.svg';
  static const trash = 'assets/icons/trash.svg';
  static const edit = 'assets/icons/edit.svg';
  static const chevron = 'assets/icons/chevron.svg';
  static const back = 'assets/icons/back.svg';
  static const info = 'assets/icons/info.svg';
  static const wifiOff = 'assets/icons/wifi-off.svg';
  static const alert = 'assets/icons/alert.svg';
  static const flame = 'assets/icons/flame.svg';
  static const filter = 'assets/icons/filter.svg';
  static const sound = 'assets/icons/sound.svg';
  static const user = 'assets/icons/user.svg';
  static const close = 'assets/icons/close.svg';
  static const ai = 'assets/icons/ai.svg';
  static const image = 'assets/icons/image.svg';
  static const sun = 'assets/icons/sun.svg';

  static const values = [
    eye,
    history,
    settings,
    plus,
    play,
    stop,
    call,
    flag,
    check,
    shield,
    bell,
    battery,
    upload,
    film,
    camera,
    lock,
    key,
    phone,
    sms,
    logout,
    trash,
    edit,
    chevron,
    back,
    info,
    wifiOff,
    alert,
    flame,
    filter,
    sound,
    user,
    close,
    ai,
    image,
    sun,
  ];
}

@immutable
class _DuotoneColorMapper extends ColorMapper {
  const _DuotoneColorMapper({
    required this.asset,
    required this.outline,
    required this.accent,
  });

  final String asset;
  final Color outline;
  final Color accent;

  @override
  Color substitute(
    String? id,
    String elementName,
    String attributeName,
    Color color,
  ) {
    final rgb = color.toARGB32() & 0xFFFFFF;
    if (rgb == SvgSourceColors.iconOutline.toARGB32() & 0xFFFFFF) {
      return outline.withValues(alpha: outline.a * color.a);
    }
    if (rgb == SvgSourceColors.iconAccent.toARGB32() & 0xFFFFFF) {
      return accent.withValues(alpha: accent.a * color.a);
    }
    assert(
      false,
      '$asset: $attributeName ${SvgSourceColors.hex(color)} is neither '
      'duotone color',
    );
    return color;
  }

  @override
  bool operator ==(Object other) =>
      other is _DuotoneColorMapper &&
      other.asset == asset &&
      other.outline == outline &&
      other.accent == accent;

  @override
  int get hashCode => Object.hash(asset, outline, accent);
}
