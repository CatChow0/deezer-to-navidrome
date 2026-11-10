package io.github.catchow0.d2n.baselineprofile

import androidx.benchmark.macro.junit4.BaselineProfileRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Direction
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The journey the profile is recorded on: start, sign in when needed, then
 * the screens people open most. The server and the account come from the
 * instrumentation arguments d2nServer, d2nUser and d2nPassword.
 */
@RunWith(AndroidJUnit4::class)
class BaselineProfileGenerator {
    @get:Rule
    val rule = BaselineProfileRule()

    private val args = InstrumentationRegistry.getArguments()

    @Test
    fun generate() = rule.collect(packageName = "io.github.catchow0.d2n", includeInStartupProfile = true) {
        pressHome()
        startActivityAndWait()
        device.signIn()
        device.waitFor("Dashboard")
        device.scrollMain()
        device.openAndBack(By.textContains("missing"))
        for (tab in listOf("Made for you", "Stats", "Releases", "More")) {
            device.findObject(By.text(tab))?.click()
            device.waitForIdle()
            device.scrollMain()
        }
        device.findObject(By.text("Settings"))?.click()
        device.waitForIdle()
        device.pressBack()
        device.findObject(By.text("Dashboard"))?.click()
        device.waitForIdle()
    }

    private fun UiDevice.signIn() {
        if (wait(Until.hasObject(By.text("Server address")), 3_000)) {
            findObject(By.clazz("android.widget.EditText")).text = args.getString("d2nServer", "http://10.0.2.2:8097")
            findObject(By.text("Continue")).click()
        }
        if (wait(Until.hasObject(By.text("Username")), 5_000)) {
            val fields = findObjects(By.clazz("android.widget.EditText"))
            fields[0].text = args.getString("d2nUser", "admin")
            fields[1].text = args.getString("d2nPassword", "")
            findObjects(By.text("Sign in")).last().click()
        }
    }

    private fun UiDevice.waitFor(text: String) {
        check(wait(Until.hasObject(By.text(text)), 20_000)) {
            "\"$text\" never showed; on screen: " + findObjects(By.textContains("")).map { it.text }
        }
    }

    /** Down and back up the screen's list: what the profile needs of scrolling. */
    private fun UiDevice.scrollMain() {
        val list = findObject(By.scrollable(true)) ?: return
        list.setGestureMargin(displayWidth / 5)
        list.fling(Direction.DOWN)
        waitForIdle()
        list.fling(Direction.UP)
        waitForIdle()
    }

    private fun UiDevice.openAndBack(selector: androidx.test.uiautomator.BySelector) {
        val target = findObject(selector) ?: return
        target.click()
        waitForIdle()
        wait(Until.hasObject(By.scrollable(true)), 10_000)
        scrollMain()
        pressBack()
        waitForIdle()
    }
}
