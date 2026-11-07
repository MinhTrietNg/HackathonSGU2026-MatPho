import 'package:flutter/widgets.dart';

class MpStill extends StatelessWidget {
  const MpStill(this.asset, {super.key, this.size});

  static const aspectRatio = 16 / 9;

  final String asset;

  final Size? size;

  @override
  Widget build(BuildContext context) => Image.asset(
    asset,
    width: size?.width,
    height: size?.height,
    fit: BoxFit.cover,
    gaplessPlayback: true,
    excludeFromSemantics: true,
  );
}
