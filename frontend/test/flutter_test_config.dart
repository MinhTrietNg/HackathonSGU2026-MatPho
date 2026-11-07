import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/core/widgets/mp_illustration_motion.dart';

Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  TestWidgetsFlutterBinding.ensureInitialized();
  mpIllustrationMotionEnabled = false;
  if (goldenFileComparator case final LocalFileComparator local) {
    goldenFileComparator = _TolerantComparator(local.basedir);
  }
  await _loadFamily('Be Vietnam Pro', 'be_vietnam_pro', [
    'BeVietnamPro-Regular',
    'BeVietnamPro-Medium',
    'BeVietnamPro-SemiBold',
    'BeVietnamPro-Bold',
    'BeVietnamPro-ExtraBold',
  ]);
  await _loadFamily('IBM Plex Mono', 'ibm_plex_mono', [
    'IBMPlexMono-Regular',
    'IBMPlexMono-Medium',
    'IBMPlexMono-SemiBold',
  ]);
  await testMain();
}

Future<void> _loadFamily(String family, String dir, List<String> files) {
  final loader = FontLoader(family);
  for (final file in files) {
    loader.addFont(rootBundle.load('assets/fonts/$dir/$file.ttf'));
  }
  return loader.load();
}

/// Goldens are rendered on different machines, whose anti-aliasing at
/// rounded corners and text edges differs by a fraction of a percent. Accept
/// up to [_maxDiffRate] of differing pixels; anything above that fails with
/// the usual diff images.
class _TolerantComparator extends LocalFileComparator {
  _TolerantComparator(Uri basedir)
    : super(basedir.resolve('flutter_test_config.dart'));

  static const _maxDiffRate = 0.015;

  @override
  Future<bool> compare(Uint8List imageBytes, Uri golden) async {
    final result = await GoldenFileComparator.compareLists(
      imageBytes,
      await getGoldenBytes(golden),
    );
    if (result.passed || result.diffPercent <= _maxDiffRate) {
      result.dispose();
      return true;
    }
    final error = await generateFailureOutput(result, golden, basedir);
    result.dispose();
    throw FlutterError(error);
  }
}
