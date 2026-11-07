import Flutter
import UIKit
import UserNotifications
import AVFoundation
import AudioToolbox

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  private var audioPlayer: AVAudioPlayer?
  private var vibrateTimer: Timer?

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    UNUserNotificationCenter.current().delegate = self as? UNUserNotificationCenterDelegate
    registerFireAlertCategory()
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    if let registrar = engineBridge.pluginRegistry.registrar(forPlugin: "MatPhoSirenPlugin") {
      let channel = FlutterMethodChannel(
        name: "com.matpho.mat_pho/siren",
        binaryMessenger: registrar.messenger()
      )
      channel.setMethodCallHandler { [weak self] call, result in
        switch call.method {
        case "start":
          self?.startSiren()
          result(nil)
        case "stop":
          self?.stopSiren()
          result(nil)
        default:
          result(FlutterMethodNotImplemented)
        }
      }
    }
  }

  private func registerFireAlertCategory() {
    let callAction = UNNotificationAction(
      identifier: "call114",
      title: "Gọi 114",
      options: [.foreground]
    )
    let viewAction = UNNotificationAction(
      identifier: "view",
      title: "Xem",
      options: [.foreground]
    )
    let category = UNNotificationCategory(
      identifier: "FIRE_ALERT_CATEGORY",
      actions: [callAction, viewAction],
      intentIdentifiers: [],
      options: [.customDismissAction]
    )
    UNUserNotificationCenter.current().setNotificationCategories([category])
  }

  private func startSiren() {
    DispatchQueue.main.async { [weak self] in
      guard let self = self else { return }
      do {
        // .playback ignores the hardware Mute/Silent switch on iPhone
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playback, mode: .default, options: [.duckOthers])
        try session.setActive(true)

        if let url = Bundle.main.url(forResource: "fire_alarm_siren", withExtension: "wav") {
          if self.audioPlayer == nil {
            self.audioPlayer = try AVAudioPlayer(contentsOf: url)
            self.audioPlayer?.numberOfLoops = -1 // Infinite loop
            self.audioPlayer?.volume = 1.0
            self.audioPlayer?.prepareToPlay()
          }
          if self.audioPlayer?.isPlaying == false {
            self.audioPlayer?.play()
          }
        }
      } catch {
        print("Failed to start iOS fire siren: \(error)")
      }

      // Continuous vibration loop on iPhone
      self.vibrateTimer?.invalidate()
      AudioServicesPlayAlertSound(SystemSoundID(kSystemSoundID_Vibrate))
      self.vibrateTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { _ in
        AudioServicesPlayAlertSound(SystemSoundID(kSystemSoundID_Vibrate))
      }
    }
  }

  private func stopSiren() {
    DispatchQueue.main.async { [weak self] in
      guard let self = self else { return }
      self.vibrateTimer?.invalidate()
      self.vibrateTimer = nil
      if self.audioPlayer?.isPlaying == true {
        self.audioPlayer?.stop()
      }
      self.audioPlayer = nil
      try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }
  }
}
