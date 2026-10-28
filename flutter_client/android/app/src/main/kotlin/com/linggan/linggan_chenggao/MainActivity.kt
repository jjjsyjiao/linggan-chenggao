package com.linggan.linggan_chenggao

import android.content.ActivityNotFoundException
import android.content.ClipData
import android.content.Intent
import android.graphics.BitmapFactory
import android.net.Uri
import android.webkit.MimeTypeMap
import androidx.core.content.FileProvider
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.util.UUID
import java.util.concurrent.Executors

class MainActivity : FlutterActivity() {
    private val preparationExecutor = Executors.newSingleThreadExecutor()
    private var shareChannel: MethodChannel? = null
    private var preparingShare = false

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        shareChannel = MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            "xhs_notes/share"
        ).apply {
            setMethodCallHandler { call, result ->
                if (call.method == "shareImages") {
                    shareImages(call, result)
                } else {
                    result.notImplemented()
                }
            }
        }
    }

    private fun shareImages(call: MethodCall, result: MethodChannel.Result) {
        val rawPaths = call.argument<List<*>>("paths")
        if (rawPaths.isNullOrEmpty() || rawPaths.any { it !is String || it.isBlank() }) {
            result.error("invalid_arguments", "请先选择需要分享的图片。", null)
            return
        }
        if (preparingShare) {
            result.error("share_busy", "正在准备图片，请稍候。", null)
            return
        }
        val paths = rawPaths.filterIsInstance<String>()
        preparingShare = true
        preparationExecutor.execute {
            try {
                val uris = prepareImageUris(paths)
                runOnUiThread {
                    preparingShare = false
                    if (isFinishing || isDestroyed) {
                        result.error("share_unavailable", "当前页面无法打开分享，请重新尝试。", null)
                        return@runOnUiThread
                    }
                    launchImageShare(uris, result)
                }
            } catch (error: Exception) {
                runOnUiThread {
                    preparingShare = false
                    result.error(
                        if (error is InvalidImageException) "invalid_image" else "share_failed",
                        error.localizedMessage ?: "图片准备失败，请重新选择图片。",
                        null
                    )
                }
            }
        }
    }

    // Copy on a worker thread and expose only this small cache subtree. Do not
    // remove a session as soon as the app returns: receivers can read it later.
    private fun prepareImageUris(paths: List<String>): ArrayList<Uri> {
        val root = File(cacheDir, "share_images").apply { mkdirs() }
        val cutoff = System.currentTimeMillis() - 24 * 60 * 60 * 1000L
        root.listFiles()?.filter { it.isDirectory && it.lastModified() < cutoff }
            ?.forEach { runCatching { it.deleteRecursively() } }
        val session = File(root, UUID.randomUUID().toString())
        check(session.mkdirs()) { "无法创建图片分享缓存，请检查设备存储空间。" }
        try {
            return ArrayList(paths.mapIndexed { index, path ->
                val source = File(path)
                if (!source.isFile || !source.canRead()) {
                    throw InvalidImageException("第 ${index + 1} 张图片不可读取，请重新选择。")
                }
                val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                BitmapFactory.decodeFile(source.absolutePath, options)
                if (options.outWidth <= 0 || options.outHeight <= 0 ||
                    options.outMimeType?.startsWith("image/") != true
                ) {
                    throw InvalidImageException("第 ${index + 1} 个文件不是可分享的图片。")
                }
                val extension = MimeTypeMap.getSingleton()
                    .getExtensionFromMimeType(options.outMimeType) ?: "jpg"
                val copy = File(session, "image_${index + 1}.$extension")
                source.copyTo(copy)
                FileProvider.getUriForFile(this, "$packageName.note_images", copy)
            })
        } catch (error: Exception) {
            session.deleteRecursively()
            throw error
        }
    }

    private fun imageIntent(uris: ArrayList<Uri>): Intent {
        return Intent(
            if (uris.size == 1) Intent.ACTION_SEND else Intent.ACTION_SEND_MULTIPLE
        ).apply {
            type = "image/*"
            if (uris.size == 1) {
                putExtra(Intent.EXTRA_STREAM, uris.first())
            } else {
                putParcelableArrayListExtra(Intent.EXTRA_STREAM, uris)
            }
            // ClipData makes read permission apply to every shared URI.
            clipData = ClipData.newUri(contentResolver, "笔记图片", uris.first()).apply {
                uris.drop(1).forEach { addItem(ClipData.Item(it)) }
            }
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
    }

    private fun launchImageShare(uris: ArrayList<Uri>, result: MethodChannel.Result) {
        val shareIntent = imageIntent(uris)
        val xhsIntent = Intent(shareIntent).setPackage("com.xingin.xhs")
        if (xhsIntent.resolveActivity(packageManager) != null) {
            try {
                startActivity(xhsIntent)
                result.success(mapOf("status" to "launched", "destination" to "xiaohongshu"))
                return
            } catch (_: ActivityNotFoundException) {
                // The app can be removed between resolving and launching.
            } catch (_: SecurityException) {
                // An OEM or receiving app may restrict its share activity.
            }
        }
        try {
            startActivity(Intent.createChooser(shareIntent, "选择小红书分享图片"))
            // Standard Android intents cannot confirm cancellation or publishing.
            result.success(mapOf("status" to "launched", "destination" to "system"))
        } catch (_: ActivityNotFoundException) {
            result.error("share_unavailable", "未找到可接收图片的应用，请安装小红书后重试。", null)
        } catch (_: SecurityException) {
            result.error("share_failed", "系统无法授予图片读取权限，请重新选择图片后重试。", null)
        }
    }

    override fun cleanUpFlutterEngine(flutterEngine: FlutterEngine) {
        shareChannel?.setMethodCallHandler(null)
        shareChannel = null
        super.cleanUpFlutterEngine(flutterEngine)
    }

    override fun onDestroy() {
        preparationExecutor.shutdown()
        super.onDestroy()
    }
}

class NoteImageProvider : FileProvider()

private class InvalidImageException(message: String) : Exception(message)
