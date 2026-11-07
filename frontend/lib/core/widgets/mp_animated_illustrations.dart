import 'package:flutter/widgets.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../theme/theme.dart';
import 'mp_illustration.dart';
import 'mp_illustration_motion.dart';
import 'mp_illustration_motions.dart';

class MpOtpIllustration extends StatelessWidget {
  const MpOtpIllustration({super.key, required this.size});

  final Size size;

  static const _fourthDot = 'Vector_10';

  @override
  Widget build(BuildContext context) {
    return MpAnimatedIllustration(
      motion: MpIllustrationMotions.otp,
      size: size,
      still: SvgPicture.asset(
        MpIllustrations.otp,
        width: size.width,
        height: size.height,
        excludeFromSemantics: true,
        colorMapper: _OtpColorMapper(context.mpColors),
      ),
    );
  }
}

@immutable
class _OtpColorMapper extends ColorMapper {
  const _OtpColorMapper(this.colors);

  final MpColors colors;

  @override
  Color substitute(
    String? id,
    String elementName,
    String attributeName,
    Color color,
  ) {
    if (id == MpOtpIllustration._fourthDot) return colors.brandAccent;
    final token = SvgSourceColors.illustration(
      colors,
      color,
      groundShadow: id == MpIllustration.groundShadowId,
    );
    assert(
      token != null,
      'ill/otp: $attributeName ${SvgSourceColors.hex(color)} has no token in '
      'SvgSourceColors.illustration',
    );
    if (token == null) return color;
    return token.withValues(alpha: token.a * color.a);
  }

  @override
  bool operator ==(Object other) =>
      other is _OtpColorMapper && identical(other.colors, colors);

  @override
  int get hashCode => identityHashCode(colors);
}

class MpPermNotifyIllustration extends StatelessWidget {
  const MpPermNotifyIllustration({
    super.key,
    this.size = MpIllustration.figmaSize,
  });

  final Size size;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    String hex(Color color) => SvgSourceColors.hex(color);
    final svg =
        '''
<svg width="280" height="180" viewBox="0 0 280 180" fill="none" xmlns="http://www.w3.org/2000/svg">
<g transform="translate(22 14)"><path d="M118 156C183.17 156 236 121.078 236 78C236 34.9218 183.17 0 118 0C52.8304 0 0 34.9218 0 78C0 121.078 52.8304 156 118 156Z" fill="${hex(c.illBlob)}"/></g>
<g transform="translate(54 149)"><path opacity="0.7" d="M86 14C133.5 14 172 10.9 172 7C172 3.1 133.5 0 86 0C38.5 0 0 3.1 0 7C0 10.9 38.5 14 86 14Z" fill="${hex(c.illShadow)}"/></g>
<g transform="translate(103 22)"><path d="M60 0H14C6.3 0 0 6.3 0 14V116C0 123.7 6.3 130 14 130H60C67.7 130 74 123.7 74 116V14C74 6.3 67.7 0 60 0Z" fill="${hex(c.illInk)}"/></g>
<g transform="translate(108 27)"><path d="M54 0H10C4.5 0 0 4.5 0 10V110C0 115.5 4.5 120 10 120H54C59.5 120 64 115.5 64 110V10C64 4.5 59.5 0 54 0Z" fill="${hex(c.illRaised)}"/></g>
<g transform="translate(130 31)"><path d="M18 0H2C0.9 0 0 0.9 0 2C0 3.1 0.9 4 2 4H18C19.1 4 20 3.1 20 2C20 0.9 19.1 0 18 0Z" fill="${hex(c.illInk)}"/></g>
<g transform="translate(111 46)">
<path d="M51 0H7C3.1 0 0 3.1 0 7V19C0 22.9 3.1 26 7 26H51C54.9 26 58 22.9 58 19V7C58 3.1 54.9 0 51 0Z" fill="${hex(c.illSurface)}"/>
<path d="M12 20C15.9 20 19 16.9 19 13C19 9.1 15.9 6 12 6C8.1 6 5 9.1 5 13C5 16.9 8.1 20 12 20Z" fill="${hex(c.statusFire)}"/>
<path d="M48.5 7H25.5C24.1 7 23 8.1 23 9.5C23 10.9 24.1 12 25.5 12H48.5C49.9 12 51 10.9 51 9.5C51 8.1 49.9 7 48.5 7Z" fill="${hex(c.illWhite)}"/>
<path d="M41 16H25C23.9 16 23 16.9 23 18C23 19.1 23.9 20 25 20H41C42.1 20 43 19.1 43 18C43 16.9 42.1 16 41 16Z" fill="${hex(c.illLineStrong)}"/>
</g>
<g transform="translate(169 90)"><path d="M0 0C0 1.9 0.700006 3.6 2.10001 4.9C3.40001 6.3 5.1 7 7 7C8.9 7 10.6 6.3 12 4.9C13.3 3.6 14 1.9 14 0" fill="${hex(c.brandAccent)}"/></g>
<g transform="translate(147 42)"><path d="M7 36V22C7 16.2 9.29999 10.6 13.4 6.4C17.6 2.3 23.2 0 29 0C34.8 0 40.4 2.3 44.6 6.4C48.7 10.6 51 16.2 51 22V36L58 44H0L7 36Z" fill="${hex(c.brandAccent)}"/></g>
<g transform="translate(131.75 38.75)"><path d="M78.25 23.2504C78.2364 17.2781 76.6498 11.4147 73.65 6.25038M86.25 23.2504C86.2582 15.8803 84.3269 8.63779 80.65 2.25038M10.25 23.2504C10.2637 17.2781 11.8502 11.4147 14.85 6.25038M2.25003 23.2504C2.24184 15.8803 4.17317 8.63779 7.85003 2.25038" stroke-width="4.5" stroke-linecap="round" stroke="${hex(c.brandAccent)}"/></g>
</svg>''';
    return MpAnimatedIllustration(
      motion: MpIllustrationMotions.permNotify,
      size: size,
      still: SvgPicture.string(
        svg,
        width: size.width,
        height: size.height,
        excludeFromSemantics: true,
      ),
    );
  }
}
