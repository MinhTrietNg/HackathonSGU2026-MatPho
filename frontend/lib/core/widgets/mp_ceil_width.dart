import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';

class MpCeilWidth extends SingleChildRenderObjectWidget {
  const MpCeilWidth({super.key, required Widget super.child});

  @override
  RenderObject createRenderObject(BuildContext context) => _RenderCeilWidth();
}

class _RenderCeilWidth extends RenderProxyBox {
  double _ceil(double width) => width.isFinite ? width.ceilToDouble() : width;

  @override
  double computeMinIntrinsicWidth(double height) =>
      _ceil(super.computeMinIntrinsicWidth(height));

  @override
  double computeMaxIntrinsicWidth(double height) =>
      _ceil(super.computeMaxIntrinsicWidth(height));

  @override
  Size computeDryLayout(covariant BoxConstraints constraints) {
    final size = child!.getDryLayout(constraints);
    return constraints.constrain(Size(_ceil(size.width), size.height));
  }

  @override
  void performLayout() {
    child!.layout(constraints, parentUsesSize: true);
    size = constraints.constrain(
      Size(_ceil(child!.size.width), child!.size.height),
    );
  }
}
