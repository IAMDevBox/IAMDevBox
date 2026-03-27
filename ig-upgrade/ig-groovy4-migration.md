# PingGateway Groovy 4 Migration Analysis

**Applies to:** PingGateway 2024.11 (Groovy 4.0.19, upgraded from Groovy 3)

**Rule ID naming:** `X-Nxx` where N = severity (0=ERROR, 1=WARN, 2=INFO)

---

## Compilation Errors (Must Fix)

| Rule | Issue | Details | Fix |
|---|---|---|---|
| G4-001 | Old package: XmlSlurper | `groovy.util.XmlSlurper` removed | Change to `groovy.xml.XmlSlurper` |
| G4-002 | Old package: XmlParser | `groovy.util.XmlParser` removed | Change to `groovy.xml.XmlParser` |
| G4-003 | Old package: GroovyTestCase | `groovy.util.GroovyTestCase` removed | Change to `groovy.test.GroovyTestCase` |
| G4-004 | Old package: AntBuilder | `groovy.util.AntBuilder` removed | Change to `groovy.ant.AntBuilder` |

## Semantic Changes (No Error but Different Behavior)

| Rule | Issue | Groovy 3 | Groovy 4 | Fix |
|---|---|---|---|---|
| G4-101 | `intersect()` method | Draws elements from 2nd collection | Draws from 1st collection | Verify result is still correct |
| G4-102 | Array addition `b + c` | Returns `Object[]` | Returns same type as `b` | Use explicit cast or `.union()` |
| G4-103 | SQL exception type | `Sql#call` throws `Exception` | Throws `SQLException` | Change catch blocks to `catch (SQLException e)` |
| G4-104 | Private field access | Closures can access private fields | May fail in subclasses/inner classes | Use `@CompileStatic` or change to `protected` |
| G4-105 | Wildcard import | `import groovy.util.*` works | May pull in removed classes | Replace with specific imports |
| G4-106 | Removed class usage | `XmlSlurper` etc. in `groovy.util` | Removed from `groovy.util` | Verify import is from correct package |
| G4-201 | Floating-point zero | `0.0f` and `-0.0f` treated as equal | Correctly distinguished | Use `equalsIgnoreZeroSign` if needed |
| G4-202 | `getProperties()` | Returns properties only | Also returns public fields | Verify property iteration |
| G4-203 | Boolean property access | `isFoo()` works for all types | Only works for primitive `boolean` | Use `getFoo()` for `Boolean` wrapper types |

## PingGateway Script Deprecations

| Rule | Deprecated | Since | Replacement |
|---|---|---|---|
| IG-001 | `Promise.get()` | — | `thenOnResult()` or `thenAsync()` (causes deadlocks) |
| IG-002 | `Promise.getOrThrow()` | — | `thenOnResult()` or `thenAsync()` |
| IG-003 | `Promise.getOrThrowUninterruptibly()` | — | `thenOnResult()` or `thenAsync()` |
| IG-101 | `request.form` | IG 7.x | `Request.getQueryParams()`, `Entity.getForm()`, `Entity.setForm()` |
| IG-102 | `matches()` in route conditions | — | `find()` or `matchesWithRegex()` (removed in 2025.x) |
| IG-103 | `ldap` binding / `LdapClient` | IG 7.1 | Removed |
| IG-104 | `JwtSession` object | 2024.11 | `JwtSessionManager` |
| IG-105 | `"Session"` config key (uppercase) | 2024.11 | Lowercase `"session"` property |
| IG-106 | `TokenResolver` / `_token()` / `_t()` | 2024.6 | Expression `&{...}` |
| IG-107 | `request.uri` in OAuth2 filter | 2023.9 | `IdpSelectionLoginContext` |
| IG-108 | `matches()` in Groovy scripts | — | `find()` or `matchesWithRegex()` (removed in 2025.x) |
| IG-201 | `org.forgerock.util.time.Duration` | 2025.6 | `java.time.Duration` |

## Route Config Checks

| Rule | Issue | Details |
|---|---|---|
| RT-001 | Duplicate handler declarations | Same handler key appears multiple times in route JSON |
| RT-002 | Missing required config | Filter/handler missing required fields (e.g., UserProfileFilter needs `username`) |
| RT-101 | Duplicate route name/ID | Multiple route files define the same route name or ID |
| RT-102 | Deprecated `matches()` in condition | Route `"condition"` uses deprecated `matches()` function |
| RT-103 | Deprecated expressions in `${...}` | Inline expressions use deprecated functions or patterns |

## Removed Features (Groovy 4)

| Feature | Details |
|---|---|
| Antlr2 parser | Old parser completely removed, only new parser available |
| Classic bytecode generation | Only invokedynamic bytecode supported, no "-indy" jar variants |
| `StaticTypeCheckingVisitor#collectAllInterfacesByName` | Removed from public API |
| `groovy-jaxb` module | Removed (JAXB no longer in JDK) |
| `groovy-bsf` module | Removed (BSF v2 end-of-life since 2005) |
| `groovy-testng` module | Removed from `groovy-all` |

## PingGateway Built-in Objects (Available in Scripts)

| Object | Type | Description |
|---|---|---|
| `request` | Request | HTTP request |
| `response` | Response | HTTP response (response flow only) |
| `context` | Context | Context chain leaf node |
| `contexts` | Map<String, Context> | All named contexts |
| `next` | Handler | Next handler in chain |
| `session` | SessionContext | Cross-request session |
| `attributes` | AttributesContext | Single-request transient state |
| `globals` | Map | Variables persisting across invocations |
| `logger` | SLF4J Logger | Script-named logger |
| `http` | Client | Outbound HTTP client |
| `heap` | Heap | Route heap objects (`heap['Name']`) |
| `args` | Map | Custom script parameters |

## PingGateway-Specific Limitations

| Limitation | Details |
|---|---|
| UTF-8 only | Scripts must use UTF-8 encoding |
| 1-second delay after script change | Groovy interpreter needs time to detect file changes |
| Auto-compile caching | Scripts compiled on first access, recompiled only after modification |

## Checklist

### Groovy 4 — Errors (0xx)
- [ ] G4-001~004: Check `import` statements for removed package names

### Groovy 4 — Warnings (1xx)
- [ ] G4-101: Check `intersect()` usage semantics
- [ ] G4-102: Check array addition type assumptions
- [ ] G4-103: Check `catch(Exception)` blocks with SQL operations
- [ ] G4-104: Check private field access in closures
- [ ] G4-105: Check `import groovy.util.*` wildcard imports
- [ ] G4-106: Check removed class usage (`XmlSlurper`, `XmlParser`, etc.)

### Groovy 4 — Info (2xx)
- [ ] G4-201: Check floating-point zero comparisons
- [ ] G4-202: Check `getProperties()` usage
- [ ] G4-203: Check `isFoo()` on `Boolean` wrapper types

### PingGateway — Errors (0xx)
- [ ] IG-001~003: Check blocking Promise calls

### PingGateway — Warnings (1xx)
- [ ] IG-101: Check `request.form` usage
- [ ] IG-102/IG-108: Check `matches()` usage everywhere
- [ ] IG-103: Check `ldap` binding / `LdapClient`
- [ ] IG-104: Check `JwtSession` usage
- [ ] IG-105: Check uppercase `"Session"` config key
- [ ] IG-106: Check `TokenResolver` / `_token()` / `_t()`
- [ ] IG-107: Check `request.uri` in OAuth2 filter

### PingGateway — Info (2xx)
- [ ] IG-201: Check `org.forgerock.util.time.Duration`

### Route — Errors (0xx)
- [ ] RT-001: Check for duplicate handler declarations
- [ ] RT-002: Check missing required config fields

### Route — Warnings (1xx)
- [ ] RT-101: Check duplicate route names/IDs
- [ ] RT-102: Check deprecated `matches()` in conditions
- [ ] RT-103: Check deprecated expressions in `${...}`

## References

- [Groovy 4.0 Release Notes](https://groovy-lang.org/releasenotes/groovy-4.0.html)
- [PingGateway Scripts Reference](https://docs.pingidentity.com/pinggateway/2024.11/reference/Scripts.html)
- [PingGateway Deprecated Features](https://docs.pingidentity.com/pinggateway/release-notes/deprecated.html)
- [PingGateway What's New](https://docs.pingidentity.com/pinggateway/release-notes/whats-new.html)
- [ScriptableFilter](https://docs.pingidentity.com/pinggateway/2024.11/reference/ScriptableFilter.html)
