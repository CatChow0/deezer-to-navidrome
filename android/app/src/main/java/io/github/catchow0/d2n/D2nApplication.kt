package io.github.catchow0.d2n

import android.app.Application

class D2nApplication : Application() {
    val graph: AppGraph by lazy { AppGraph(this) }
}
