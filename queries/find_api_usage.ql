/**
 * @id find-api-usage
 * @name Find API usage
 * @description This script attempts to find all API usages from dependencies
 *      in package.json. Specifically, it attempts to find all flow from the
 *      import statements to function calls. It does not attempt to find other
 *      types of API usage, such as object properties or class methods, but it
 *      can track global data flow and find some non-trivial API usages.
 */

import javascript

module ImportToCallConfig implements DataFlow::ConfigSig {
  // source are import statements
  predicate isSource(DataFlow::Node source) {
    exists(NpmPackage pkg, Import imp |
      imp.getTopLevel() = pkg.getAModule() and
      // imp returns the whole import statement: import { createApp } from 'vue';
      // imp.getAChild() gets createApp
      source.asExpr() = imp.getAChild()
    )
  }

  // using any sink so we can connect with the second data flow source
  predicate isSink(DataFlow::Node sink) { any() }
}

module ConnectFlowConfig implements DataFlow::ConfigSig {
  predicate isSource(DataFlow::Node source) { any() }

  // the final sink finds function invocations
  predicate isSink(DataFlow::Node sink) {
    exists(DataFlow::InvokeNode invocation | sink = invocation.getCalleeNode())
  }
}

module RequireToCallConfig implements DataFlow::ConfigSig {
  // source is a required dependency
  predicate isSource(DataFlow::Node source) {
    exists(NpmPackage pkg, Require req |
      req.getTopLevel() = pkg.getAModule() and
      source = req.flow()
    )
  }

  // sink is a function invocation
  predicate isSink(DataFlow::Node sink) {
    exists(DataFlow::InvokeNode invocation | sink = invocation.getCalleeNode())
  }
}

module ImportToCall = TaintTracking::Global<ImportToCallConfig>;

module ConnectFlow = TaintTracking::Global<ConnectFlowConfig>;

module RequireToCall = TaintTracking::Global<RequireToCallConfig>;

predicate isDependency(string name) {
  exists(NpmPackage pkg |
    pkg.getPackageJson().getDependencies().getADependency(name, _) or
    pkg.getPackageJson().getDevDependencies().getADependency(name, _)
  )
}

predicate hasImportFlow(
  string name, ImportToCall::PathNode impSource, ConnectFlow::PathNode connSink
) {
  exists(Import imp, ImportToCall::PathNode impSink, ConnectFlow::PathNode connSource |
    imp.getAChild() = impSource.getNode().getAstNode() and
    name = imp.getImportedPath().getValue() and
    ImportToCall::flowPath(impSource, impSink) and
    // finding calls like "impSink"."connSource"
    connSource.getNode().getAstNode() = impSink.getNode().getAstNode().getParent() and
    ConnectFlow::flowPath(connSource, connSink)
  )
}

predicate hasRequireFlow(
  string name, RequireToCall::PathNode reqSource, RequireToCall::PathNode reqSink
) {
  exists(Require req |
    name = req.getImportedPath().getValue() and
    req.flow() = reqSource.getNode() and
    RequireToCall::flowPath(reqSource, reqSink)
  )
}

from
  string name, string file, int lineno, AstNode node, ImportToCall::PathNode impSource,
  ConnectFlow::PathNode connSink, RequireToCall::PathNode reqSource, RequireToCall::PathNode reqSink
where
  isDependency(name) and
  (
    hasImportFlow(name, impSource, connSink) and
    file = connSink.getNode().getFile().getRelativePath() and
    lineno = connSink.getNode().getStartLine() and
    node = connSink.getNode().getAstNode()
    or
    hasRequireFlow(name, reqSource, reqSink) and
    file = reqSink.getNode().getFile().getRelativePath() and
    lineno = reqSink.getNode().getStartLine() and
    node = reqSink.getNode().getAstNode()
  )
select name, file, lineno, node order by name, file, lineno
