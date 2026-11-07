import 'package:flutter/widgets.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../theme/theme.dart';
import 'mp_illustration_motion.dart';
import 'mp_illustration_motions.dart';

class MpIllustration extends StatelessWidget {
  const MpIllustration(
    this.asset, {
    super.key,
    this.size = figmaSize,
    this.animated = false,
    this.backdrop = true,
  }) : assert(
         !animated ||
             asset == MpIllustrations.feed ||
             asset == MpIllustrations.feedFire ||
             asset == MpIllustrations.feedSmoke,
         'only the ill/feed-* artwork has an animated variant',
       );

  static const figmaSize = Size(280, 180);

  final String asset;
  final Size size;

  final bool animated;

  final bool backdrop;

  static const groundShadowId = 'Vector_2';

  static const _themeIndependent = {
    MpIllustrations.feed,
    MpIllustrations.feedFire,
    MpIllustrations.feedSmoke,
  };

  @override
  Widget build(BuildContext context) {
    final still = _still(context);
    final motion = MpIllustrationMotions.byAsset[asset];
    if (motion == null || (_themeIndependent.contains(asset) && !animated)) {
      return still;
    }
    return MpAnimatedIllustration(
      motion: motion,
      size: size,
      still: still,
      backdrop: backdrop,
    );
  }

  Widget _still(BuildContext context) {
    return SvgPicture.asset(
      asset,
      width: size.width,
      height: size.height,
      excludeFromSemantics: true,
      colorMapper: _themeIndependent.contains(asset)
          ? (animated ? const _AnimatedFeedMapper() : null)
          : colorMapper(asset, context.mpColors, backdrop: backdrop),
    );
  }

  static ColorMapper colorMapper(
    String asset,
    MpColors colors, {
    bool backdrop = true,
  }) => _IllustrationColorMapper(asset, colors, backdrop: backdrop);
}

abstract final class MpIllustrations {
  static const onbWatch = 'assets/illustrations/onb-watch.svg';
  static const onbTwoTier = 'assets/illustrations/onb-two-tier.svg';
  static const onbCall = 'assets/illustrations/onb-call.svg';
  static const permNotify = 'assets/illustrations/perm-notify.svg';
  static const permBattery = 'assets/illustrations/perm-battery.svg';
  static const otp = 'assets/illustrations/otp.svg';
  static const reset = 'assets/illustrations/reset.svg';
  static const emptySource = 'assets/illustrations/empty-source.svg';
  static const upload = 'assets/illustrations/upload.svg';
  static const uploadError = 'assets/illustrations/upload-error.svg';
  static const watching = 'assets/illustrations/watching.svg';
  static const verifying = 'assets/illustrations/verifying.svg';
  static const fire = 'assets/illustrations/fire.svg';
  static const unverified = 'assets/illustrations/unverified.svg';
  static const dismissed = 'assets/illustrations/dismissed.svg';
  static const safe = 'assets/illustrations/safe.svg';
  static const learn = 'assets/illustrations/learn.svg';
  static const emptyHistory = 'assets/illustrations/empty-history.svg';
  static const offline = 'assets/illustrations/offline.svg';
  static const serverError = 'assets/illustrations/server-error.svg';
  static const slowDevice = 'assets/illustrations/slow-device.svg';
  static const success = 'assets/illustrations/success.svg';
  static const logout = 'assets/illustrations/logout.svg';
  static const delete = 'assets/illustrations/delete.svg';
  static const feed = 'assets/illustrations/feed.svg';
  static const feedFire = 'assets/illustrations/feed-fire.svg';
  static const feedSmoke = 'assets/illustrations/feed-smoke.svg';
  static const share = 'assets/illustrations/share.svg';
  static const invite = 'assets/illustrations/invite.svg';
  static const camScan = 'assets/illustrations/cam-scan.svg';
  static const camOffline = 'assets/illustrations/cam-offline.svg';

  static const values = [
    onbWatch,
    onbTwoTier,
    onbCall,
    permNotify,
    permBattery,
    otp,
    reset,
    emptySource,
    upload,
    uploadError,
    watching,
    verifying,
    fire,
    unverified,
    dismissed,
    safe,
    learn,
    emptyHistory,
    offline,
    serverError,
    slowDevice,
    success,
    logout,
    delete,
    feed,
    feedFire,
    feedSmoke,
    share,
    invite,
    camScan,
    camOffline,
  ];
}

@immutable
class _AnimatedFeedMapper extends ColorMapper {
  const _AnimatedFeedMapper();

  static const _lightCones = {'Vector_5', 'Vector_6'};

  @override
  Color substitute(
    String? id,
    String elementName,
    String attributeName,
    Color color,
  ) => _lightCones.contains(id) ? color.withValues(alpha: 0) : color;
}

@immutable
class _IllustrationColorMapper extends ColorMapper {
  const _IllustrationColorMapper(
    this.asset,
    this.colors, {
    required this.backdrop,
  });

  final String asset;
  final MpColors colors;
  final bool backdrop;

  @override
  Color substitute(
    String? id,
    String elementName,
    String attributeName,
    Color color,
  ) {
    if (!backdrop && SvgSourceColors.isIllustrationBlob(color)) {
      return color.withValues(alpha: 0);
    }
    final token = SvgSourceColors.illustration(
      colors,
      color,
      groundShadow: id == MpIllustration.groundShadowId,
    );
    assert(
      token != null,
      '$asset: $attributeName ${SvgSourceColors.hex(color)} has no token in '
      'SvgSourceColors.illustration',
    );
    if (token == null) return color;
    return token.withValues(alpha: token.a * color.a);
  }

  @override
  bool operator ==(Object other) =>
      other is _IllustrationColorMapper &&
      other.asset == asset &&
      identical(other.colors, colors) &&
      other.backdrop == backdrop;

  @override
  int get hashCode => Object.hash(asset, identityHashCode(colors), backdrop);
}
