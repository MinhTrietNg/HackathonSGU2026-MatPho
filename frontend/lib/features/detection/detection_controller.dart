import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/models/models.dart';
import '../../data/providers.dart';
import '../../data/repositories/repositories.dart';

final detectionControllerProvider = NotifierProvider.autoDispose
    .family<DetectionController, DetectionState, String>(
      DetectionController.new,
    );

class DetectionController extends Notifier<DetectionState> {
  DetectionController(this.cameraId);

  final String cameraId;

  late DetectionRepository _repository;
  StreamSubscription<DetectionState>? _session;

  bool _ended = false;

  @override
  DetectionState build() {
    final repository = ref.watch(detectionRepositoryProvider);
    _repository = repository;
    ref.onDispose(() {
      _session?.cancel();
      _session = null;
      if (!_ended) unawaited(repository.stop());
    });
    return const DetectionIdle();
  }

  void start(Camera camera) {
    _session?.cancel();
    _ended = false;
    _session = _repository
        .start(camera)
        .listen((next) => state = next, onDone: () => _ended = true);
  }

  void dismissSuspect() => unawaited(_repository.dismissSuspect());
}
