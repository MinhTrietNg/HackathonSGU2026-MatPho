import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import 'package:mat_pho/core/theme/theme.dart';
import 'package:mat_pho/core/widgets/mp_brand.dart';
import 'package:mat_pho/core/widgets/mp_duotone_icon.dart';
import 'package:mat_pho/core/widgets/mp_illustration.dart';

class IconSheet extends StatelessWidget {
  const IconSheet({super.key, this.active = true});

  static const size = Size(840, 403);

  final bool active;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final label = context.mpText.mono.copyWith(color: c.textSecondary);
    const columns = 7;
    return _Sheet(
      size: size,
      child: Column(
        spacing: 12,
        children: [
          for (var i = 0; i < MpIcons.values.length; i += columns)
            Row(
              spacing: 12,
              children: [
                for (final icon in MpIcons.values.skip(i).take(columns))
                  Container(
                    width: 96,
                    height: 71,
                    padding: const EdgeInsets.only(top: 12),
                    decoration: BoxDecoration(
                      color: c.bgCard,
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Column(
                      spacing: 6,
                      children: [
                        MpDuotoneIcon(
                          icon,
                          outline: active ? c.textPrimary : c.textMuted,
                          accent: active ? c.brandAccent : c.textMuted,
                        ),
                        Text(_name(icon), style: label, maxLines: 1),
                      ],
                    ),
                  ),
              ],
            ),
        ],
      ),
    );
  }
}

class IllustrationSheet extends StatelessWidget {
  const IllustrationSheet({super.key});

  static const size = Size(1680, 1681);

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final label = context.mpText.mono.copyWith(color: c.textSecondary);
    const columns = 5;
    return _Sheet(
      size: size,
      child: Column(
        spacing: 20,
        children: [
          for (var i = 0; i < MpIllustrations.values.length; i += columns)
            Row(
              spacing: 20,
              children: [
                for (final ill in MpIllustrations.values.skip(i).take(columns))
                  Container(
                    width: 300,
                    height: 223,
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: c.bgSurface,
                      borderRadius: BorderRadius.circular(14),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      spacing: 6,
                      children: [
                        MpIllustration(ill),
                        Text('ill/${_name(ill)}', style: label, maxLines: 1),
                      ],
                    ),
                  ),
              ],
            ),
        ],
      ),
    );
  }
}

class BrandSheet extends StatelessWidget {
  const BrandSheet({super.key});

  static const size = Size(658, 160);

  @override
  Widget build(BuildContext context) {
    return _Sheet(
      size: size,
      child: Stack(
        children: [
          Positioned(
            left: 0,
            top: 20,
            child: SvgPicture.asset(MpBrand.logoMark),
          ),
          Positioned(
            left: 176,
            top: 0,
            child: SvgPicture.asset(MpBrand.appIcon),
          ),
          Positioned(
            left: 386,
            top: 42,
            child: SvgPicture.asset(MpBrand.logoLockup),
          ),
        ],
      ),
    );
  }
}

class _Sheet extends StatelessWidget {
  const _Sheet({required this.size, required this.child});

  final Size size;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return SizedBox.fromSize(
      size: size,
      child: ColoredBox(
        color: context.mpColors.bgBase,
        child: Align(alignment: Alignment.topLeft, child: child),
      ),
    );
  }
}

String _name(String asset) => asset.split('/').last.replaceAll('.svg', '');
