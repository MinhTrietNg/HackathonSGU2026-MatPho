import '../models/camera.dart';
import '../models/detection_state.dart';

abstract interface class DetectionRepository {
  Stream<DetectionState> start(Camera camera);

  Future<void> dismissSuspect();

  Future<void> stop();
}
