import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;

import 'package:mat_pho/core/theme/appearance.dart';
import '../fakes/fake_scenario.dart';
import '../fakes/fake_overrides.dart';

class GalleryScope extends StatefulWidget {
  const GalleryScope({
    super.key,
    this.cases = const {},
    this.overrides = const [],
    required this.child,
  });

  final Set<FakeCase> cases;
  final List<Override> overrides;
  final Widget child;

  @override
  State<GalleryScope> createState() => _GalleryScopeState();
}

class _GalleryScopeState extends State<GalleryScope> {
  late final _container = ProviderContainer(
    overrides: fakeOverrides([
      fakeScenarioProvider.overrideWithValue(
        FakeScenario.test(cases: widget.cases),
      ),
      lightAppearanceProvider.overrideWith(
        () => LightAppearance(
          initial: Theme.of(context).brightness == Brightness.light,
        ),
      ),
      ...widget.overrides,
    ]),
  );

  @override
  void dispose() {
    _container.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) =>
      UncontrolledProviderScope(container: _container, child: widget.child);
}
