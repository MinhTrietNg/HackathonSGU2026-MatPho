import 'package:flutter/material.dart';

import 'mp_colors.dart';
import 'mp_typography.dart';

extension MpThemeContext on BuildContext {
  MpColors get mpColors => Theme.of(this).extension<MpColors>()!;

  MpTypography get mpText => Theme.of(this).extension<MpTypography>()!;
}
