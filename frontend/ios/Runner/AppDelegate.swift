import Flutter
import UIKit
import UserNotifications
import AVFoundation
import AudioToolbox

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  private var audioPlayer: AVAudioPlayer?
  private var vibrateTimer: Timer?

  // iOS plays a notification sound once and never loops it, so a fire alert
  // keeps ringing by re-delivering copies of itself back to back until the
  // user acts on it. The gap equals the length of fire_alarm_siren.wav (28 s);
  // iOS keeps at most 64 pending requests per app, so 60 copies ring ~28 min.
  private static let repeatPrefix = "matpho-fire-repeat-"
  private static let repeatGap: TimeInterval = 28
  private static let repeatCount = 60

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
          self?.cancelRepeats()
          result(nil)
        case "repeat":
          if let args = call.arguments as? [String: Any],
             let id = args["id"] as? Int {
            self?.scheduleRepeats(of: String(id))
          }
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

  // Copies the delivered alert (keeping its userInfo, so a tap on any copy
  // reaches Dart like a tap on the original) and schedules the copies.
  private func scheduleRepeats(of identifier: String, attempt: Int = 0) {
    let center = UNUserNotificationCenter.current()
    center.getDeliveredNotifications { [weak self] delivered in
      guard let self = self else { return }
      guard let original = delivered.first(where: {
        $0.request.identifier == identifier
      }) else {
        // The alert may not be delivered yet right after it was added.
        if attempt < 10 {
          DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
            self.scheduleRepeats(of: identifier, attempt: attempt + 1)
          }
        }
        return
      }
      guard let content = original.request.content.mutableCopy()
        as? UNMutableNotificationContent else { return }
      content.threadIdentifier = "matpho-fire-\(identifier)"
      for k in 1...Self.repeatCount {
        let trigger = UNTimeIntervalNotificationTrigger(
          timeInterval: Self.repeatGap * Double(k),
          repeats: false
        )
        center.add(UNNotificationRequest(
          identifier: "\(Self.repeatPrefix)\(identifier)-\(k)",
          content: content,
          trigger: trigger
        ))
      }
    }
  }

  private func cancelRepeats() {
    let center = UNUserNotificationCenter.current()
    let isRepeat: (String) -> Bool = { $0.hasPrefix(Self.repeatPrefix) }
    center.getPendingNotificationRequests { requests in
      center.removePendingNotificationRequests(
        withIdentifiers: requests.map(\.identifier).filter(isRepeat)
      )
    }
    center.getDeliveredNotifications { notifications in
      center.removeDeliveredNotifications(
        withIdentifiers: notifications.map(\.request.identifier).filter(isRepeat)
      )
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
