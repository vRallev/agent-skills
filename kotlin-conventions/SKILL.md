---
name: kotlin-conventions
description: Apply personal Kotlin structure and style conventions. Use when you create, edit, refactor, or review Kotlin .kt or .kts files.
---

# Kotlin Conventions

Unless another rule explicitly overrides these conventions, apply them.

## Class Layout

Organize class contents in this order:

1. Property declarations and initializer blocks
2. Secondary constructors
3. Method declarations
4. Companion object
5. Nested and inner class declarations

Do not sort methods alphabetically or by visibility. Keep regular methods and extension methods together. Group related code so readers can follow the class from top to bottom. Choose either higher-level-first or lower-level-first order. Use that order consistently.

### One Top-Level Class Per File

Prefer one top-level class per file. If needed, create additional files.

Prefer:

`Class1.kt`

```kotlin
class Class1 {}
```

`Class2.kt`

```kotlin
class Class2 {}
```

Do not use:

`Classes.kt`

```kotlin
class Class1 {}

class Class2 {}
```

## Explicit Backing Fields

If the project's Kotlin version supports explicit backing fields, use them when a property exposes a read-only type with a mutable implementation.

For `MutableStateFlow`, expose a `StateFlow` property with `field = MutableStateFlow(...)`. Update the flow through the property inside the class. Avoid a separate mutable backing property and `asStateFlow()` for this pattern.

Prefer:

```kotlin
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update

class Counter {
  val count: StateFlow<Int>
    field = MutableStateFlow(0)

  fun increment() {
    count.update { it + 1 }
  }
}
```

Avoid:

```kotlin
class Counter {
  private val mutableCount = MutableStateFlow(0)
  val count: StateFlow<Int> = mutableCount.asStateFlow()

  fun increment() {
    mutableCount.update { it + 1 }
  }
}
```

See [Kotlin explicit backing fields](https://kotlinlang.org/docs/properties.html#explicit-backing-fields) and the [Storymile review comment](https://github.com/vRallev/storymile/pull/28/changes#r4192194958).

## Braces for Multiline If/Else

If an `if`/`else` statement or expression does not fit on one line, always use braces for both branches.

Prefer:

```kotlin
val logo =
  if (AppTheme.colorScheme.surfaceContainer.luminance() < 0.5f) {
    Res.drawable.storymile_logo_dark
  } else {
    Res.drawable.storymile_logo_light
  }
```

Avoid:

```kotlin
val logo =
  if (AppTheme.colorScheme.surfaceContainer.luminance() < 0.5f) Res.drawable.storymile_logo_dark
  else Res.drawable.storymile_logo_light
```

See the [Storymile pull request](https://github.com/vRallev/storymile/pull/29/changes#diff-987f4b68673f68a90db1f987b17a3ad09a91e185d7a9693750aa09e518dacf7c).

## KDoc

Use KDoc only for caller information beyond the declaration and its types. Explain the API's intent, use, observable behavior, and non-obvious edge cases.

If requirements, architectural goals, encapsulation constraints, implementation details, or design reasons do not help callers use the API, omit them.

Prefer:

```kotlin
/**
 * Adds [interceptor] to the end of the request pipeline.
 *
 * An interceptor can return a response without invoking later interceptors.
 */
fun addInterceptor(interceptor: RequestInterceptor)
```

Avoid:

```kotlin
/** Configures request behavior without exposing its internal backend state. */
interface FakeServerControl
```

## Lambdas Over Method References

Prefer lambdas over method references. For example, use `abc.doSomething { it.abc() }` instead of `abc.doSomething(Abc::abc)`.

## Inline Unshared Constants

Do not extract constants without a reason. If a value is not shared, keep it inline.

Do:

```kotlin
class Class1 {
  fun hello() {
    println("Test")
  }
}
```

Do not use:

```kotlin
class Class1 {
  fun hello() {
    println(TEST_MESSAGE)
  }
}

private const val TEST_MESSAGE = "Test"
```

## Smallest Possible Scope

Use the smallest possible scope for language constructs. If only one class uses an extension function, nest it inside that class. Do not declare it as a private top-level function next to the class.

For an extension function used by one class, do:

```kotlin
class Class1 {
  fun hello() {
    "Test".inConsole()
  }

  private fun String.inConsole() = println(this)
}
```

Do not use:

```kotlin
class Class1 {
  fun hello() {
    "Test".inConsole()
  }
}

private fun String.inConsole() = println(this)
```

For a constant used by one class, do:

```kotlin
class Class1 {
  fun hello1() {
    println(PROFILE_PICTURE_KEY)
  }

  fun hello2() {
    println(PROFILE_PICTURE_KEY)
  }

  private companion object {
    const val PROFILE_PICTURE_KEY = "profile-picture"
  }
}
```

Do not use:

```kotlin
class Class1 {
  fun hello1() {
    println(PROFILE_PICTURE_KEY)
  }

  fun hello2() {
    println(PROFILE_PICTURE_KEY)
  }
}

private const val PROFILE_PICTURE_KEY = "profile-picture"
```
