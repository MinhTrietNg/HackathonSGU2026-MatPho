import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/core/widgets/mp_illustration_motion.dart';

Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  TestWidgetsFlutterBinding.ensureInitialized();
  mpIllustrationMotionEnabled = false;
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
