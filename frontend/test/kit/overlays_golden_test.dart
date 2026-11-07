import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/core/widgets/mp_banner.dart';
import '../gallery/entries/kit_overlays.dart';
import '../gallery/gallery_registry.dart';

import '../helpers/golden.dart';

void main() {
  for (final demo in kitOverlayDemos) {
    testWidgets('overlay ${demo.code}', (tester) async {
      await pumpGoldenScreen(
        tester,
        Builder(builder: findGalleryEntry(demo.code)!.builder),
      );
      await tester.runAsync(() => Future<void>.delayed(Duration.zero));
      await tester.pumpAndSettle();
      await expectLater(
        goldenFinder,
        matchesGoldenFile('../goldens/kit/${demo.code}.png'),
      );
    });
  }

  for (final board in kitBannerBoards) {
    testWidgets('banner ${board.code}', (tester) async {
      await pumpGoldenComponent(
        tester,
        Align(
          alignment: Alignment.topLeft,
          child: SizedBox(
            width: board.size.width,
            child: Builder(builder: board.builder),
          ),
        ),
        size: board.size,
      );
      expect(tester.getSize(find.byType(MpBanner)), board.size);
      await expectLater(
        goldenFinder,
        matchesGoldenFile('../goldens/kit/${board.code}.png'),
      );
    });
  }
}
