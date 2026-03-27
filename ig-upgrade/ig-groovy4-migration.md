# PingGateway Groovy 4 Migration Analysis

**Applies to:** PingGateway 2024.11 (Groovy 4.0.19, upgraded from Groovy 3)

---

## Compilation Errors (Must Fix)

| Rule | Issue | Details | Fix |
|---|---|---|---|
| G4-001 | Old package: XmlSlurper | `groovy.util.XmlSlurper` removed | Change to `groovy.xml.XmlSlurper` |
| G4-002 | Old package: XmlParser | `groovy.util.XmlParser` removed | Change to `groovy.xml.XmlParser` |
| G4-003 | Old package: GroovyTestCase | `groovy.util.GroovyTestCase` removed | Change to `groovy.test.GroovyTestCase` |
| G4-004 | Old package: AntBuilder | `groovy.util.AntBuilder` removed | Change to `groovy.ant.AntBuilder` |
| G4-005 | Boolean property access | `isFoo()` only works for primitive `boolean`, not `Boolean` wrapper | Use `getFoo()` for `Boolean` wrapper types |
| G4-012 | Wildcard import | `import groovy.util.*` may pull in removed classes | Replace with specific imports from `groovy.xml`, `groovy.test`, `groovy.ant` |
| G4-010 | Private field access | Closure accessing private fields of subclasses/inner classes may fail | Use `@CompileStatic` or change to `protected` |
| G4-009 | SQL exception type | `Sql#call` variants now throw `SQLException` instead of `Exception` | Change catch blocks to `catch (SQLException e)` |

## Semantic Changes (No Error but Different Behavior)

| Rule | Issue | Groovy 3 | Groovy 4 | Fix |
|---|---|---|---|---|
| G4-006 | `intersect()` method | Draws elements from 2nd collection | Draws from 1st collection | Verify result is still correct |
| G4-011 | Array addition `b + c` | Returns `Object[]` | Returns same type as `b` | Use explicit cast or `.union()` |
| G4-007 | Floating-point zero | `0.0f` and `-0.0f` treated as equal | Correctly distinguished | Use `equalsIgnoreZeroSign` if needed |
| G4-008 | `getProperties()` | Returns properties only | Also returns public fields | Verify property iteration |

## PingGateway Script Deprecations

| Rule | Deprecated | Since | Replacement |
|---|---|---|---|
| IG-001 | `request.form` | IG 7.x | `Request.getQueryParams()`, `Entity.getForm()`, `Entity.setForm()` |
| IG-002 | `Promise.get()` | — | `thenOnResult()` or `thenAsync()` (causes deadlocks) |
| IG-003 | `Promise.getOrThrow()` | — | `thenOnResult()` or `thenAsync()` |
| IG-004 | `Promise.getOrThrowUninterruptibly()` | — | `thenOnResult()` or `thenAsync()` |
| IG-006 | `ldap` binding / `LdapClient` | IG 7.1 | Removed |
| IG-007 | `JwtSession` object | 2024.11 | `JwtSessionManager` |
| IG-009 | `TokenResolver` / `_token()` / `_t()` | 2024.6 | Expression `&{...}` |
| IG-010 | `org.forgerock.util.time.Duration` | 2025.6 | `java.time.Duration` |
| IG-011 | `request.uri` in OAuth2 filter | 2023.9 | `IdpSelectionLoginContext` |

## PingGateway Route Config Deprecations

| Rule | Deprecated | Since | Replacement |
|---|---|---|---|
| IG-005 | `matches()` in route conditions | — | Use `find()` or `matchesWithRegex()` (removed in 2025.x) |
| IG-008 | `"Session"` config key (uppercase) | 2024.11 | Lowercase `"session"` property |
| IG-012 | `matches()` in Groovy scripts | — | Use `find()` or `matchesWithRegex()` (removed in 2025.x) |
| RT-005 | `matches()` in `${...}` expressions | — | Use `find()` or `matchesWithRegex()` (removed in 2025.x) |

## Route Config Checks

| Rule | Issue | Details |
|---|---|---|
| RT-001 | Duplicate handler declarations | Same handler key appears multiple times in route JSON |
| RT-002 | Missing required config | Filter/handler missing required fields (e.g., UserProfileFilter needs `username`) |
| RT-003 | Duplicate route name/ID | Multiple route files define the same route name or ID |
| RT-005 | Deprecated `matches()` in condition | Route `"condition"` uses deprecated `matches()` function |
| RT-006 | Deprecated expressions in `${...}` | Inline expressions use deprecated functions or patterns |

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

### Groovy 4 Migration
- [ ] G4-001~004: Check `import` statements for removed package names
- [ ] G4-005: Check `isFoo()` on `Boolean` wrapper types
- [ ] G4-006: Check `intersect()` usage semantics
- [ ] G4-007: Check floating-point zero comparisons
- [ ] G4-008: Check `getProperties()` usage
- [ ] G4-009: Check `catch(Exception)` blocks with SQL operations
- [ ] G4-010: Check private field access in closures
- [ ] G4-011: Check array addition type assumptions

### PingGateway Script Deprecations
- [ ] IG-001: Check `request.form` usage
- [ ] IG-002~004: Check blocking Promise calls
- [ ] IG-006: Check `ldap` binding / `LdapClient`
- [ ] IG-007: Check `JwtSession` usage
- [ ] IG-009: Check `TokenResolver` / `_token()` / `_t()`
- [ ] IG-010: Check `org.forgerock.util.time.Duration`
- [ ] IG-011: Check `request.uri` in OAuth2 filter

### Route Config
- [ ] IG-005/IG-012/RT-005: Check `matches()` usage everywhere
- [ ] IG-008: Check uppercase `"Session"` config key
- [ ] RT-001: Check for duplicate handler declarations
- [ ] RT-002: Check missing required config fields
- [ ] RT-003: Check duplicate route names/IDs

## References

- [Groovy 4.0 Release Notes](https://groovy-lang.org/releasenotes/groovy-4.0.html)
- [PingGateway Scripts Reference](https://docs.pingidentity.com/pinggateway/2024.11/reference/Scripts.html)
- [PingGateway Deprecated Features](https://docs.pingidentity.com/pinggateway/release-notes/deprecated.html)
- [PingGateway What's New](https://docs.pingidentity.com/pinggateway/release-notes/whats-new.html)
- [ScriptableFilter](https://docs.pingidentity.com/pinggateway/2024.11/reference/ScriptableFilter.html)
