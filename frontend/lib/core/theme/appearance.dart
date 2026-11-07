import 'package:flutter_riverpod/flutter_riverpod.dart';

final lightAppearanceProvider = NotifierProvider<LightAppearance, bool>(
  LightAppearance.new,
);

class LightAppearance extends Notifier<bool> {
  LightAppearance({this.initial = false});

  final bool initial;

  @override
  bool build() => initial;

  void set(bool light) => state = light;
}
