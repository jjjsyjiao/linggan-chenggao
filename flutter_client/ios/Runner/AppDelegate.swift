import Flutter
import ImageIO
import UIKit
import UniformTypeIdentifiers

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  private var shareChannel: FlutterMethodChannel?
  private var pendingShareResult: FlutterResult?
  private let imagePreparationQueue = DispatchQueue(
    label: "com.linggan.note-image-sharing", qos: .userInitiated
  )

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    let channel = FlutterMethodChannel(
      name: "xhs_notes/share",
      binaryMessenger: engineBridge.applicationRegistrar.messenger()
    )
    channel.setMethodCallHandler { [weak self] call, result in
      guard call.method == "shareImages" else {
        result(FlutterMethodNotImplemented)
        return
      }
      guard let self = self else {
        result(FlutterError(code: "share_unavailable", message: "当前页面无法打开分享。", details: nil))
        return
      }
      self.shareImages(arguments: call.arguments, result: result)
    }
    shareChannel = channel
  }

  private func shareImages(arguments: Any?, result: @escaping FlutterResult) {
    guard let arguments = arguments as? [String: Any],
      let paths = arguments["paths"] as? [String],
      !paths.isEmpty, paths.allSatisfy({ !$0.isEmpty }),
      let origin = arguments["origin"] as? [String: NSNumber],
      let x = origin["x"]?.doubleValue, let y = origin["y"]?.doubleValue,
      let width = origin["width"]?.doubleValue, let height = origin["height"]?.doubleValue,
      x.isFinite, y.isFinite, width.isFinite, height.isFinite, width > 0, height > 0
    else {
      result(FlutterError(code: "invalid_arguments", message: "请选择图片后重新分享。", details: nil))
      return
    }
    guard pendingShareResult == nil else {
      result(FlutterError(code: "share_busy", message: "上一次分享还没有结束。", details: nil))
      return
    }
    pendingShareResult = result
    let anchor = CGRect(x: x, y: y, width: width, height: height)
    imagePreparationQueue.async { [weak self] in
      guard let self = self else { return }
      do {
        let images = try self.prepareImages(paths)
        DispatchQueue.main.async {
          self.presentShare(images: images, anchor: anchor)
        }
      } catch {
        DispatchQueue.main.async {
          let failure = error as? ImageShareFailure
          self.finishShare(FlutterError(
            code: failure?.code ?? "share_failed",
            message: failure?.message ?? "图片准备失败，请检查设备存储空间并重新选择图片。",
            details: nil
          ))
        }
      }
    }
  }

  // Validate image headers and copy files without decoding full-resolution
  // UIImages. Share extensions can read these files after presentation ends.
  private func prepareImages(_ paths: [String]) throws -> [ImageShareItem] {
    let manager = FileManager.default
    let cache = try manager.url(for: .cachesDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
    let root = cache.appendingPathComponent("note_share_images", isDirectory: true)
    try manager.createDirectory(at: root, withIntermediateDirectories: true)
    let cutoff = Date(timeIntervalSinceNow: -24 * 60 * 60)
    if let children = try? manager.contentsOfDirectory(
      at: root, includingPropertiesForKeys: [.contentModificationDateKey, .isDirectoryKey]
    ) {
      for child in children {
        if let values = try? child.resourceValues(forKeys: [.contentModificationDateKey, .isDirectoryKey]),
          values.isDirectory == true, let modified = values.contentModificationDate, modified < cutoff {
          try? manager.removeItem(at: child)
        }
      }
    }
    let session = root.appendingPathComponent(UUID().uuidString, isDirectory: true)
    try manager.createDirectory(at: session, withIntermediateDirectories: true)
    do {
      return try paths.enumerated().map { index, path in
        let source = URL(fileURLWithPath: path)
        guard manager.isReadableFile(atPath: path),
          let imageSource = CGImageSourceCreateWithURL(source as CFURL, nil),
          CGImageSourceGetCount(imageSource) > 0,
          let type = CGImageSourceGetType(imageSource),
          let properties = CGImageSourceCopyPropertiesAtIndex(imageSource, 0, nil) as? [CFString: Any],
          let pixelWidth = properties[kCGImagePropertyPixelWidth] as? NSNumber,
          let pixelHeight = properties[kCGImagePropertyPixelHeight] as? NSNumber,
          pixelWidth.intValue > 0, pixelHeight.intValue > 0
        else {
          throw ImageShareFailure(code: "invalid_image", message: "第 \(index + 1) 张图片无法读取，请重新选择。")
        }
        let identifier = type as String
        let fileExtension = UTType(identifier)?.preferredFilenameExtension ?? source.pathExtension
        let destination = session.appendingPathComponent("image_\(index + 1).\(fileExtension)")
        try manager.copyItem(at: source, to: destination)
        return ImageShareItem(url: destination, typeIdentifier: identifier)
      }
    } catch {
      try? manager.removeItem(at: session)
      throw error
    }
  }

  private func presentShare(images: [ImageShareItem], anchor: CGRect) {
    guard let scene = UIApplication.shared.connectedScenes
      .compactMap({ $0 as? UIWindowScene })
      .first(where: { $0.activationState == .foregroundActive }),
      let root = scene.windows.first(where: { $0.isKeyWindow })?.rootViewController
    else {
      finishShare(FlutterError(code: "share_unavailable", message: "请返回应用后重新分享。", details: nil))
      return
    }
    var presenter = root
    while let presented = presenter.presentedViewController {
      presenter = presented
    }
    guard !presenter.isBeingDismissed, !presenter.isBeingPresented,
      presenter.viewIfLoaded?.window != nil
    else {
      finishShare(FlutterError(code: "share_busy", message: "请关闭当前弹窗后重新分享。", details: nil))
      return
    }
    let controller = UIActivityViewController(activityItems: images, applicationActivities: nil)
    controller.completionWithItemsHandler = { [weak self] _, completed, _, error in
      if let error = error {
        self?.finishShare(FlutterError(code: "share_failed", message: error.localizedDescription, details: nil))
      } else {
        self?.finishShare([
          "status": completed ? "completed" : "cancelled",
          "destination": "system",
        ])
      }
    }
    if let popover = controller.popoverPresentationController {
      popover.sourceView = presenter.view
      let converted = root.view.convert(anchor, to: presenter.view)
      let visible = converted.intersection(presenter.view.bounds)
      popover.sourceRect = visible.isNull || visible.isEmpty
        ? CGRect(x: presenter.view.bounds.midX, y: presenter.view.bounds.midY, width: 1, height: 1)
        : visible
      popover.permittedArrowDirections = []
    }
    presenter.present(controller, animated: true)
  }

  private func finishShare(_ value: Any?) {
    let result = pendingShareResult
    pendingShareResult = nil
    result?(value)
  }
}

private struct ImageShareFailure: Error {
  let code: String
  let message: String
}

private final class ImageShareItem: NSObject, UIActivityItemSource {
  let url: URL
  let typeIdentifier: String

  init(url: URL, typeIdentifier: String) {
    self.url = url
    self.typeIdentifier = typeIdentifier
  }

  func activityViewControllerPlaceholderItem(_ activityViewController: UIActivityViewController) -> Any {
    return url
  }

  func activityViewController(
    _ activityViewController: UIActivityViewController,
    itemForActivityType activityType: UIActivity.ActivityType?
  ) -> Any? {
    return url
  }

  func activityViewController(
    _ activityViewController: UIActivityViewController,
    dataTypeIdentifierForActivityType activityType: UIActivity.ActivityType?
  ) -> String {
    return typeIdentifier
  }
}
