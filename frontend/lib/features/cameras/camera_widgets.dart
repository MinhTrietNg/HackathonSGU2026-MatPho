library;

import 'package:flutter/material.dart';

import '../../core/theme/theme.dart';
import '../../core/widgets/mp_illustration.dart';

double normalHeight(double fontSize) => (fontSize * 1.265).round() / fontSize;

class CameraSheet extends StatelessWidget {
  const CameraSheet({
    super.key,
    required this.padding,
    required this.spacing,
    required this.handleColor,
    required this.centerHandle,
    required this.children,
  });

  final EdgeInsets padding;
  final double spacing;
  final Color handleColor;

  final bool centerHandle;
  final List<Widget> children;

  static const _radius = Radius.circular(24);

  @override
  Widget build(BuildContext context) {
    final bottom =
        MediaQuery.paddingOf(context).bottom +
        MediaQuery.viewInsetsOf(context).bottom;
    return Container(
      padding: padding.copyWith(bottom: padding.bottom + bottom),
      decoration: BoxDecoration(
        color: context.mpColors.bgSurface,
        borderRadius: const BorderRadius.only(
          topLeft: _radius,
          topRight: _radius,
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: centerHandle
            ? CrossAxisAlignment.center
            : CrossAxisAlignment.start,
        spacing: spacing,
        children: [
          Container(
            width: 40,
            height: 4,
            decoration: BoxDecoration(
              color: handleColor,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          Flexible(
            child: SingleChildScrollView(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                spacing: spacing,
                children: children,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class CameraArtBox extends StatelessWidget {
  const CameraArtBox({
    super.key,
    required this.art,
    required this.artSize,
    required this.height,
    this.overlay,
    this.pictureUrl,
  });

  final String art;
  final Size artSize;
  final double height;
  final Widget? overlay;
  final String? pictureUrl;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: height,
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: context.mpColors.bgSurface,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Stack(
        fit: StackFit.expand,
        children: [
          OverflowBox(
            minWidth: 0,
            minHeight: 0,
            maxWidth: double.infinity,
            maxHeight: double.infinity,
            child: MpIllustration(art, size: artSize),
          ),
          if (pictureUrl case final url?)
            Image.network(
              url,
              fit: BoxFit.fill,
              errorBuilder: (_, _, _) => const SizedBox.shrink(),
            ),
          ?overlay,
        ],
      ),
    );
  }
}
