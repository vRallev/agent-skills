---
name: kotlin-conventions
description: Apply personal Kotlin structure and style conventions. Use whenever creating, editing, refactoring, or reviewing Kotlin .kt or .kts files.
---

# Kotlin Conventions

Apply these conventions unless another rule explicitly overrides them.

## Class Layout

Organize class contents in this order:

1. Property declarations and initializer blocks
2. Secondary constructors
3. Method declarations
4. Companion object

Do not sort method declarations alphabetically or by visibility, and do not separate regular methods from extension methods. Group related code so that someone reading the class from top to bottom can follow its logic. Choose either higher-level-first or lower-level-first ordering and apply it consistently.

### One Top-Level Class Per File

Prefer one top-level class per file. Create additional files when necessary.

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

## Lambdas Over Method References

Prefer lambdas over method references. For example, use `abc.doSomething { it.abc() }` instead of `abc.doSomething(Abc::abc)`.

## Inline Unshared Constants

Do not extract constants merely for the sake of extraction. Inline values that are not shared.

Do:

```kotlin
class Class1 {
  fun hello() {
    println("Test")
  }
}
```

Don't:

```kotlin
class Class1 {
  fun hello() {
    println(TEST_MESSAGE)
  }
}

private const val TEST_MESSAGE = "Test"
```

## Smallest Possible Scope

Use the smallest possible scope for language constructs. For example, nest an extension function used by only one class inside that class rather than declaring it as a private top-level function next to the class.

For an extension function used by one class, do:

```kotlin
class Class1 {
  fun hello() {
    "Test".inConsole()
  }

  private fun String.inConsole() = println(this)
}
```

Don't:

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

Don't:

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
