package com.example.fixture;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * ApiSurface fixture: one controller, one path prefix, one endpoint, and two
 * param bindings -- one explicitly named, one relying on javac -parameters,
 * which is the fragile case api_surface__param_binding exists to flag.
 */
@RestController
@RequestMapping("/fixture")
public class ControllerFixture {

    @GetMapping("/ping")
    public String ping(@RequestParam("name") String name, @RequestParam String other) {
        return "pong " + name + other;
    }
}
