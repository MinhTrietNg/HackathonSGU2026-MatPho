import 'package:flutter/widgets.dart';

class MpFillScrollView extends StatelessWidget {
  const MpFillScrollView({super.key, required this.child, this.physics});

  final Widget child;

  final ScrollPhysics? physics;

  @override
  Widget build(BuildContext context) {
    return CustomScrollView(
      physics: physics,
      slivers: [SliverFillRemaining(hasScrollBody: false, child: child)],
    );
  }
}
