package com.example.fixture;

import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/** Both annotation stacks in one file, as in the target repo. */
@RestController
@Api(value = "legacy-catalog")
@Tag(name = "catalog")
public class OpenApiFixture {

  @GetMapping("/documented")
  @ApiOperation(value = "Swagger 2 summary")
  @Operation(summary = "OpenAPI 3 summary", description = "longer text")
  @io.swagger.v3.oas.annotations.media.Schema(description = "inline fully-qualified")
  public String documented() {
    return "ok";
  }
}
